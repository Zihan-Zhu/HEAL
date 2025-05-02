import os
import json
import random
import ast
import asyncio
import docx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import httpx
from datetime import datetime
from dotenv import load_dotenv
from sse_starlette.sse import EventSourceResponse


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

load_dotenv()

LLM_API_KEY = os.environ.get("OPENAI_API_KEY")
LLM_API_ENDPOINT = "https://api.openai.com/v1/chat/completions"

DATA_DIR = "patient_data"
os.makedirs(DATA_DIR, exist_ok=True)

class Conversation(BaseModel):
    messages: List[dict]
    patient_id: Optional[str] = None

PATIENT_INFO_FIELDS = [
    "name", "age", "gender", "presenting_problem", "associated_symptoms", "primary_survey", "focused_assessment", "pertinent_history", "red_flags"
]

MONITORING_INFO_FIELDS = ["condition_change"]

# ATS categories and their corresponding maximum waiting times
WAITING_TIMES = {
    'Category 1 (Immediate)': 'Immediate',
    'Category 2 (Emergency)': '10 minutes',
    'Category 3 (Urgent)': '30 minutes',
    'Category 4 (Semi-urgent)': '60 minutes',
    'Category 5 (Non-urgent)': '120 minutes'
}

patient_info_dict = {
    "patient_id": "",
    "name": "",
    "age": "",
    "gender": "",
    "arrival_time": "",
    "presenting_problem": "",
    "associated_symptoms": "",
    "primary_survey":{
        "A": "",
        "B": "",
        "C": "",
        "D": "",
        "E": ""
    },
    "focused_assessment": "",
    "pertinent_history": "",
    "red_flags": ""
}


monitoring_info_dict = {
    "retriage_time": "", 
    "condition_change": ""
}

# Store all patient info from both modes (temporal var)
patient_data = {}

@app.post("/chat") # Registration and Triage Mode
async def chat(conversation: Conversation):
    global patient_info_dict, patient_data

    # Initialize patient_id if not provided
    if not conversation.patient_id:
        conversation.patient_id = generate_patient_id()
        patient_info_dict['patient_id'] = conversation.patient_id
        patient_info_dict['arrival_time'] = datetime.now().isoformat()

    # Extract information periodically
    #if len(conversation.messages) == 6:
        #new_info = await extract_patient_info(conversation.messages[-6:], patient_info_dict)
        #patient_info_dict.update({k: v for k, v in new_info.items() if v})
        #update_patient_info_dict(patient_info_dict, new_info)
    if len(conversation.messages) > 2 and len(conversation.messages) % 2 == 0:
        #new_info = await extract_patient_info(conversation.messages[-2:], patient_info_dict)
        #update_patient_info_dict(patient_info_dict, new_info)
        try:
            new_info = await extract_patient_info(conversation.messages[-2:], patient_info_dict)
            update_patient_info_dict(patient_info_dict, new_info)
        except Exception as e:
            #print(f"Error during extract_patient_info: {e}")
            try:
                fallback_messages = conversation.messages[-4:] if len(conversation.messages) >= 4 else conversation.messages
                new_info = await extract_patient_info(fallback_messages, patient_info_dict)
                update_patient_info_dict(patient_info_dict, new_info)
            except Exception as e:
                print(f"Error during fallback extract_patient_info: {e}")

    print(f"patient_info_dict: {patient_info_dict}")

    # Update patient_data whenever new information is extracted
    if conversation.patient_id:
        if conversation.patient_id not in patient_data:
            patient_data[conversation.patient_id] = {}
        patient_data[conversation.patient_id].update(patient_info_dict)
    
    print(f"patient_data: {patient_data}")

    # Check if all required fields are filled
    #info_complete = all(patient_info_dict.values())
    info_complete = check_info_complete(patient_info_dict)
    if info_complete or len(conversation.messages) >= 28:
        # We label an ATS category for this patient
        ats_category = await get_ats_category(patient_info_dict)
        #print(ats_category)
        ats_category = ast.literal_eval(ats_category)
        patient_info_dict.update(ats_category)

        # Update the patient data
        patient_data[conversation.patient_id].update(patient_info_dict)
        # Get the corresponding waiting time using the global WAITING_TIMES
        waiting_time = WAITING_TIMES.get(patient_info_dict["ats_category"])

        patient_file = f"{DATA_DIR}/{conversation.patient_id}.json"
        with open(patient_file, 'w') as f:
            json.dump(patient_info_dict, f, indent=2)

        # Create an empty monitoring file
        monitoring_file = f"{DATA_DIR}/{conversation.patient_id}_monitoring.json"
        if not os.path.exists(monitoring_file):
            with open(monitoring_file, 'w') as f:
                pass

        #response = f"Thank you for providing all the necessary information. Your patient ID is {conversation.patient_id}. Please keep this for future reference."

        response = f"""Thank you for providing all the necessary information. Your patient ID is {conversation.patient_id}. Please keep this for future reference.
                    Based on the information you've provided, you have been assigned to ATS {patient_info_dict["ats_category"]}. The maximum waiting time for this category is {waiting_time}.
                    Please note that this is an initial assessment, and priority may change based on ongoing evaluations and the condition of other patients in the emergency department."""

        
        # Reset the dictionary for the next patient
        patient_info_dict = {
            "patient_id": "",
            "name": "",
            "age": "",
            "gender": "",
            "arrival_time": "",
            "presenting_problem": "",
            "associated_symptoms": "",
            "primary_survey":{
                "A": "",
                "B": "",
                "C": "",
                "D": "",
                "E": ""
            },
            "focused_assessment": "",
            "pertinent_history": "",
            "red_flags": ""
        }

        # Reset the entire conversation
        conversation.messages = []
        conversation.patient_id = None  # Reset patient_id to None for the next conversation
    else:
        chat_system_message = read_word_file("Chat_Prompts.docx")
        # Continue the conversation
        system_message = {
            "role": "system", 
            "content": f"""{chat_system_message}"""
        }
        
        print(f"conversation history: {conversation.messages}")
        #context = f"Current patient data: {json.dumps(patient_info_dict)}"
        messages = [system_message] + conversation.messages + [{"role": "user", "content": f"Please continue the conversation and ensure each new question focus on a different and uncovered topic (i.e., any field with an empty string) from {patient_info_dict}"}]

        response = await call_llm(messages)

    return {
        "response": response,
        "patient_id": conversation.patient_id,
        "info_complete": info_complete
    }


@app.post("/monitor_patient") # Monitoring Mode
async def monitor_patient(conversation: Conversation):
    global monitoring_info_dict, patient_data

    # If this is the first message, provide the greeting
    #if len(conversation.messages) == 0:
        #return {
            #"response": "Welcome to the ED Patient Monitoring System. Please enter your patient ID to track your condition.",
            #"patient_id": None,
           # "reset_conversation": False
        #}

    #print(f"conversation length: {conversation.messages}")


    # If patient_id is not provided, assume it's in the last message
    if not conversation.patient_id:
        potential_id = conversation.messages[-1]['content'].strip()
        monitoring_file = f"{DATA_DIR}/{potential_id}_monitoring.json"
        
        if os.path.exists(monitoring_file):
            conversation.patient_id = potential_id
            monitoring_info_dict["retriage_time"] = datetime.now().isoformat()
        else:
            return {
                "response": "Patient ID not found. Please check your ID and try again.",
                "patient_id": None,
                "reset_conversation": False
            }

    patient_file = f"{DATA_DIR}/{conversation.patient_id}.json"
    monitoring_file = f"{DATA_DIR}/{conversation.patient_id}_monitoring.json"

    # Read patient information
    with open(patient_file, 'r') as f:
        patient_info = json.load(f)
    
    if len(conversation.messages) > 2 and len(conversation.messages) % 2 == 0:
        new_info = await extract_monitoring_info(conversation.messages, patient_info)
        monitoring_info_dict.update({k: v for k, v in new_info.items() if v})

    #print(conversation.messages)
    print(monitoring_info_dict)

    # Update patient_data with monitoring information
    if conversation.patient_id:
        if conversation.patient_id not in patient_data:
            patient_data[conversation.patient_id] = {}
        patient_data[conversation.patient_id].update(monitoring_info_dict)

    if len(conversation.messages) > 2:
        retriage_result = await retriage_complete(patient_info, conversation.messages[2:])
        #print(retriage_result["is_complete"])

    # End the conversation
    if len(conversation.messages) > 2 and len(conversation.messages) % 2 == 0 and retriage_result["is_complete"] == True:

        # Now we assign an ATS label based on the patient_info + monitoring_info_dict
        ats_category = await get_ats_category(patient_info, monitoring_info_dict)
        ats_category = ast.literal_eval(ats_category)
        monitoring_info_dict["ats_category_retriage"] = ats_category["ats_category"]

        patient_data[conversation.patient_id].update(monitoring_info_dict)

        # Check whether the monitoring file is empty or not
        with open(monitoring_file, 'r') as f:
                file_content = f.read().strip()
                if file_content:
                    monitoring_data = json.loads(file_content)
                else:
                    monitoring_data = []

        # Update the monitoring data
        monitoring_data.append(monitoring_info_dict)

        # Write updated data back to file
        with open(monitoring_file, 'w') as f:
            json.dump(monitoring_data, f, indent=2)
        

        # final response
        response = generate_final_response(
            initial_category=patient_info.get("ats_category"),
            new_category=monitoring_info_dict["ats_category_retriage"],
            waiting_time=WAITING_TIMES.get(monitoring_info_dict["ats_category_retriage"])
        )
        
        # Reset the dictionary for the next monitoring session
        monitoring_info_dict = {
            "retriage_time": "", 
            "condition_change": ""
        }

        # Reset the entire conversation
        conversation.messages = []
        conversation.patient_id = None

        return {
            "response": response,
            "patient_id": conversation.patient_id,
            "reset_conversation": True
        }


    # Continue the conversation (monitoring info hasn't been collected completely)

    # Read existing monitoring data (if any) -> we do not use it here anymore
    #with open(monitoring_file, 'r') as f:
            #file_content = f.read().strip()
            #if file_content:
                #monitoring_data = json.loads(file_content)
            #else:
                #monitoring_data = []
    
    system_message = {
        "role": "system", 
        "content": f"""You are an experienced emergency department (ED) triage nurse with a reputation for your expertise, empathy, and efficiency. 
        Your current task is to conduct a focused reassessment of a patient waiting in the ED, gathering crucial information about any changes in their condition since their initial triage.

        Patient's initial triage information: {json.dumps(patient_info)}

        Key Instructions:
        1. Start with a general, open-ended question about the patient's current state if the conversation is just beginning.
        2. Gradually become more specific, focusing on areas relevant to their initial presentation and potential changes.
        3. Pay particular attention to any new symptoms, worsening of existing symptoms, or improvement in their condition.
        4. Be alert for any red flags or urgent changes that may require immediate medical attention.
        5.	Maintain a professional yet warm and empathetic tone throughout the interaction.
	    6.	Ask one question at a time to avoid overwhelming the patient.
	    7.	Frame questions to encourage detailed responses, while keeping them concise and clear.
	    8.	Adapt your questions based on the patient’s previous responses and initial triage information.
	    9.	If the patient mentions any new concerns, follow up appropriately.
	    10.	Avoid repeating questions that have already been asked and answered in the conversation.

        Remember, your goal is to efficiently gather information about any changes in the patient's condition that might affect their triage category or required care.

        Review the conversation history provided, and then generate the next single question you would ask this patient, considering all the information you have.
        """
    }

    messages = [system_message] + conversation.messages + [{"role": "user", "content": "Please continue the conversation by asking the next appropriate question."}]

    response = await call_llm(messages)

    return {
        "response": response,
        "patient_id": conversation.patient_id,
        "reset_conversation": False
    }


@app.get("/dashboard/{patient_id}")
async def dashboard(patient_id: str):
    async def event_generator():
        patient_file = f"{DATA_DIR}/{patient_id}.json"
        monitoring_file = f"{DATA_DIR}/{patient_id}_monitoring.json"
        
        while True:
            # Initialize empty dict if patient_id not in patient_data but files exist
            if (os.path.exists(patient_file) or os.path.exists(monitoring_file)) and patient_id not in patient_data:
                patient_data[patient_id] = {}
                
            if patient_id in patient_data:
                if os.path.exists(patient_file) and os.path.getsize(patient_file) > 0:
                    with open(patient_file, 'r') as f:
                        patient_data[patient_id].update(json.load(f))
                        
                if os.path.exists(monitoring_file) and os.path.getsize(monitoring_file) > 0:
                    with open(monitoring_file, 'r') as f:
                        patient_data[patient_id].update(json.load(f)[-1])
                
                yield {
                    "event": "update",
                    "data": json.dumps(patient_data[patient_id])
                }
            
            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())


async def call_llm(messages):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            LLM_API_ENDPOINT,
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            json={
                "model": "gpt-4o-mini",
                "messages": messages,
                "temperature": 0
            }
        )
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Error calling LLM API")
        return response.json()["choices"][0]["message"]["content"]

# Patient Info Collector
async def extract_patient_info(conversation, curr_status):
    system_message = {
        "role": "system",
        "content": f"""You are an advanced AI assistant designed to extract and summarize patient information from conversations in an emergency department (ED) setting. Your task is to analyze the provided conversation and extract the following information if available: {', '.join(PATIENT_INFO_FIELDS)}

                    Key Instructions
                    1. Analyze the entire conversation thoroughly.
                    2. Extract relevant information for each field.
                    3. Summarize the essential information accurately and completely. Do not simply copy the patient's words verbatim; instead, synthesize the information into clear, concise summaries.
                    4. Ensure that your summaries capture the full meaning and context of the information provided in the conversation.
                    5. Consider the current monitoring status, which indicates whether certain fields have already been extracted: {curr_status}
                    For fields that have already been extracted, gradually add new information if found in the conversation. In particular, update the “red_flags” field if any new red flags are identified in the conversation.
                    If the patient explicitly expresses a desire to change specific fields, you may safely overwrite those fields.
                    6. At times, the assistant's question may already contain the field name you're trying to extract. If you're unsure where to assign the patient's response, use this context as a guide.
                    7. Respond with a Python dictionary containing the extracted and summarized information. Use empty strings for fields not found in the conversation.
                    8. If the patient provides an answer related to any of these fields (even if it's a negative response like 'no', 'none', or 'nope'), accurately capture this input in the corresponding field instead of leaving it as an empty string.
                    9. If no red flags are identified during the conversation, explicitly fill the “red_flags” field with 'No obvious red flags'.

                    Field Descriptions and Extraction Guidelines
                    Presenting problem and Associated symptoms
                    Identify the primary reason for the ED visit
                    Look for descriptions of symptoms, their duration, and potential triggers
                    Extract any mentioned life-threatening conditions or urgent symptoms

                    Primary survey (ABCDE)
                    Extract information related to (indicative only):
                    1. Airway (A): Patency issues, risks mentioned
                    2. Breathing (B): Respiratory rate, distress level, any breathing difficulties noted
                    3. Circulation (C): Heart rate, blood pressure, skin condition, fluid balance issues
                    4. Disability (D): Consciousness level, behaviour changes, pain score (if given)
                    5. Environment (E): For example, body temperature, skin abnormalities mentioned

                    Focused assessment
                    Identify any additional physiological data mentioned related to the presenting problem
                    Note any specific body systems assessed

                    Pertinent history
                    Extract relevant health information, focusing on:
                    1. Medications mentioned (especially those relevant to current symptoms)
                    2. Medical history and co-morbidities discussed
                    3. Allergies stated

                    Red flags
                    Carefully review the following content and identify any mentioned red flags within the conversation:
                    1. Environmental red flags:
                    - A person who is verbally or physically aggressive
                    - A person presenting with a communicable disease, such as COVID-19, influenza or varicella
                    - A disaster event - when there is a rapid increase in unwell or injured patients exceeding the hospital's capacity for safe treatment
                    2. Clinical red flags:
                    Clinical red flags are cues identified in the patient's physical assessment or history that indicate the presence of actual or potential serious illness or injury.
                    3. Physiological red flags:
                    - Identified from the primary survey or from focused body region or systems assessments
                    - Examples: an absent pulse in an injured limb, or abdominal distension in a patient with abdominal pain indicating the need for urgent assessment and treatment
                    4. Historical red flags:
                    A. Red flags relating to the presenting problem:
                        - High-risk problems, such as poisoning or overdose, which require time-critical treatment
                        - High-risk signs or symptoms, such as sudden onset of severe headache
                        - High-risk mechanism of injury, such as vehicle rollover
                        - Re-presentation to ED with the same clinical problem
                        - Recent use of drugs or alcohol
                    B. Red flags relating to the patient's health history:
                        - Extremes of age (very young - aged 18 years and below; very old - aged 65 years and over)
                        - High-risk co-morbidity relevant to the presenting condition, such as vomiting in a renal dialysis patient or fever in a patient with a ventriculoatrial shunt
                        - Multimorbidity - the presence of multiple diseases or conditions, acute or chronic
                        - Pertinent medications, such as anticoagulants because they increase the risk of bleeding
                        - Cognitive impairment
                        - Communication challenges, such as with patients from culturally and linguistically diverse communities
                        - Risk of harm, such as domestic or family violence, child abuse, elder abuse or neglect

                    Response Format
                    Your response should strictly follow the format below. Do not include any other text outside the brackets:
                    {{
                        "name": "",
                        "age": "",
                        "gender": "",
                        "presenting_problem": "",
                        "associated_symptoms": "",
                        "primary_survey": {{
                            "A": "",
                            "B": "",
                            "C": "",
                            "D": "",
                            "E": ""
                        }},
                        "focused_assessment": "",
                        "pertinent_history": "",
                        "red_flags": ""
                    }}

                    Example Response
                    Here's an example to guide your response:
                    {{
                        "name": "Jack",
                        "age": "55",
                        "gender": "Male",
                        "presenting_problem": "Self-presents with severe abdominal pain. Sudden onset 1 hour ago. Not relieved by paracetamol",
                        "associated_symptoms": "Feels nauseated, denies vomiting/ diarrhoea/dysuria",
                        "primary_survey": {{
                            "A": "patent",
                            "B": "RR 28 mild increase work of breathing",
                            "C": "pale and clammy HR 110",
                            "D": "alert and orientated, pain 10/10",
                            "E": "T 36.6 °C"
                        }},
                        "focused_assessment": "Abdomen soft, tender over right lower quadrant",
                        "pertinent_history": "None",
                        "red_flags": "very old"
                    }}

                    """
    }
    
    messages = [system_message] + [{"role": "user", "content": f"Extract patient information from this conversation: {json.dumps(conversation)}"}]
    
    response = await call_llm(messages)
    
    try:
        extracted_info = ast.literal_eval(response)
        return {field: extracted_info.get(field, "") for field in PATIENT_INFO_FIELDS}
    except (SyntaxError, ValueError):
        print("Error parsing dictionary from LLM response")
        return {field: "" for field in PATIENT_INFO_FIELDS}

# Condition Change Collector
async def extract_monitoring_info(conversation, patient_info):
    system_message = {
        "role": "system",
        "content": f"""You are an expert AI medical assistant specializing in emergency department (ED) triage. 
        Your task is to analyze conversations between ED staff and patients, extracting crucial information about changes in the patient's condition since their initial triage.

        Patient Initial Triage Information:
        {json.dumps(patient_info, indent=2)}

        Key Instructions
        1. Compare the conversation content with the initial patient information provided.
        2. Identify and summarize any changes in the patient's symptoms or overall condition since the initial assessment.
        3. Focus on changes that may affect the patient's triage category or required care.
        4. Be alert for any new symptoms, worsening of existing symptoms, or unexpected improvements.
        5. Detect any red flags or urgent changes that may require immediate medical attention.

        Response Format
        Your response should be strictly in the following Python dictionary format. Do not include any other text outside the brackets:
                {{
                    "condition_change": "Detailed summary of condition changes"
                }}

        Ensure your summary is concise yet comprehensive, capturing all significant changes that could influence triage decisions or patient care. If no relevant changes are detected, state "No significant changes reported" in the summary.
        """
    }
    
    messages = [system_message] + [{"role": "user", "content": f"Extract key condition changes from this conversation: {json.dumps(conversation)}"}]
    
    response = await call_llm(messages)
    
    try:
        extracted_info = ast.literal_eval(response)
        #print(extracted_info)
        return extracted_info
    except (SyntaxError, ValueError):
        print("Error parsing dictionary from LLM response")
        return {field: "" for field in MONITORING_INFO_FIELDS}


async def get_recommendations(monitoring_info):
    system_message = {
        "role": "system",
        "content": """You are a helpful hospital assistant tasked with providing recommendations based on patient monitoring information.
        Your recommendations should be communicated directly to the patient in a manner that is easy to understand. 
        Ensure your language is kind, empathetic, and supportive, prioritizing the patient's comfort and well-being.
        Analyze the Patient's Information and Monitoring Information carefully to provide appropriate care recommendations that are tailored to the patient's current condition."""
    }
    
    messages = [system_message] + [{"role": "user", "content": f"Provide recommendations based on this patient data: {json.dumps(monitoring_info)}"}]
    
    response = await call_llm(messages)
    return response

# Triage Category Classifier
async def get_ats_category(patient_info, monitoring_info=None):
    ats_system_message = read_word_file("ATS_Prompts.docx")
    system_message = {
        "role": "system",
        "content": f"""{ats_system_message}"""
    }
    #messages = [system_message] + [{"role": "user", "content": f"Please assign the most appropriate ATS category based on this patient triage information: {patient_info}"}]
    if monitoring_info:
        user_content = f"Please assign the most appropriate ATS category based on the initial patient triage information: {json.dumps(patient_info)} and the subsequent monitoring information: {json.dumps(monitoring_info)}"
    else:
        user_content = f"Please assign the most appropriate ATS category based on this patient triage information: {json.dumps(patient_info)}"

    messages = [system_message, {"role": "user", "content": user_content}]
    
    response = await call_llm(messages)
    return response

# Based on patient_info and the re-triage conversation with patient, decide whether we've collected enough condition change information from the patient OR there is an urgent condition change of patient (Conversation Monitor Bot)
async def retriage_complete (patient_info, conversation):
    system_message = {
        "role": "system",
        "content": f"""You are an experienced emergency department (ED) triage nurse deciding if a re-triage conversation with a patient should conclude.

        Your goal is to decide whether the current conversation with the patient has yielded enough information about changes in their condition to warrant a re-assessment of their triage category. 

        Consideration Factors:
        1. The patient's initial information and triage category
        2. Any significant changes in the patient's symptoms or condition
        3. New information that might affect the patient's triage category
        4. The patient's own assessment of their condition changes
        5. Any red flags or urgent symptoms that have developed

        Conversation Ending Guidelines:
        1. You MUST end the conversation immediately (i.e., "is_complete": True) if urgent, life-threatening symptoms are reported
        2. For non-urgent cases, you should continue the conversation (i.e., "is_complete": False) if the current dialogue is short (fewer than 4-5 exchanges) OR All aspects of the patient's condition haven't been thoroughly explored OR There's any potential for gathering more relevant information
        3. Consider ending if the patient indicates they have nothing more to add
        4. Conclude the conversation if it becomes circular, unproductive, or strays from the patient’s initial information

        Your response should be strictly in the following Python dictionary format, without providing any additional reasons. Do not include any other text outside the brackets:
        {{
            "is_complete": boolean value ("True" or "False")
        }}
        """
    }
    messages = [system_message] + [{"role": "user", "content": f"Based on the patient's initial information: {json.dumps(patient_info)} and the current conversation: {json.dumps(conversation)}, please determine if we have sufficient information for re-triage."}]
    
    response = await call_llm(messages)

    return ast.literal_eval(response)

# Generate unique patient id
def generate_patient_id():
    """
    Collect all existing patient IDs by inspecting filenames in DATA_DIR.
    """
    existing_ids = set()
    for filename in os.listdir(DATA_DIR):
        if filename.endswith(".json"):
            # Extract the ID part from the filename before '_monitoring' or '.json'
            patient_id = filename.split("_")[0].split(".")[0]
            existing_ids.add(patient_id)
    
    while True:
        patient_id_gen = str(random.randint(10000, 99999))
        if patient_id_gen not in existing_ids:
            return patient_id_gen
    

def read_word_file(filepath):
    doc = docx.Document(filepath)
    full_text = []
    for paragraph in doc.paragraphs:
        full_text.append(paragraph.text)
    return '\n'.join(full_text)

def update_patient_info_dict(patient_info_dict, new_info):
    for key, value in new_info.items():
        if key == 'primary_survey':
            for sub_key, sub_value in value.items():
                if sub_value:  # Only update if the new value is not empty
                    patient_info_dict['primary_survey'][sub_key] = sub_value
        elif value:  # Only update if the new value is not empty
            patient_info_dict[key] = value

def check_info_complete(patient_info_dict):
    # Check all top-level fields except 'primary_survey'
    top_level_complete = all(value for key, value in patient_info_dict.items() if key != 'primary_survey')
    
    # Check all fields within 'primary_survey'
    primary_survey_complete = all(patient_info_dict['primary_survey'].values())
    
    return top_level_complete and primary_survey_complete

# Generate the final response for the monitoring mode
def generate_final_response(initial_category, new_category, waiting_time):
    response = f"""
    Thank you for providing an update on your condition. We appreciate your patience and cooperation during this reassessment process.
    Based on the changes you've reported, we have carefully reevaluated your situation. As a result:
    """

    if initial_category != new_category:
            response += f"""
            Your triage category has been updated from ATS {initial_category} to ATS {new_category}.
            This change reflects the current assessment of your medical needs.
            """
    else:
        response += f"""
        You will remain in ATS {new_category}.
        We have determined that this category still best reflects your current medical needs.
        """

    response += f"""
    The maximum waiting time for ATS {new_category} is {waiting_time}.
    If you have any questions or concerns, please don't hesitate to ask a member of our ED staff.
    """

    return response


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)