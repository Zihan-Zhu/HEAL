import React, { useState, useRef, useEffect } from "react";
import axios from "axios";
import PatientDashboard from "./PatientDashboard";


const ChatComponent = ({
  conversation,
  sendMessage,
  input,
  setInput,
  mode,
}) => {
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(scrollToBottom, [conversation]);

  return (
    <div>
      <div className="bg-gray-100 p-4 rounded-lg mb-4 h-[36rem] overflow-y-auto">
        {conversation.map((message, index) => (
          <div
            key={index}
            className={`mb-2 ${
              message.role === "user" ? "text-black" : "text-black"
            }`}
          >
            <strong>{message.role === "user" ? "You:" : "Assistant:"}</strong>{" "}
            {message.content}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>
      <div className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={(e) => e.key === "Enter" && sendMessage()}
          placeholder="Type your message here..."
          className="flex-grow border-2 gray-400 rounded px-2 py-1"
        />
        <button
          onClick={sendMessage}
          className={`px-4 py-2 text-white rounded hover:bg-opacity-80 transition-colors duration-300 ${
            mode === "registration"
              ? "bg-blue-500 hover:bg-blue-600"
              : "bg-green-500 hover:bg-green-600"
          }`}
        >
          Send
        </button>
      </div>
    </div>
  );
};

const Notification = ({ message, isVisible, onClose, mode }) => {
  useEffect(() => {
    if (isVisible) {
      const timer = setTimeout(() => {
        onClose();
      }, 2000);
      return () => clearTimeout(timer);
    }
  }, [isVisible, onClose]);

  if (!isVisible) return null;

  const bgColor = mode === "monitor" ? "bg-green-500" : "bg-blue-500";

  return (
    <div
      className={`fixed top-4 right-4 ${bgColor} text-white px-4 py-2 rounded shadow-lg`}
    >
      {message}
    </div>
  );
};

const App = () => {
  const [conversation, setConversation] = useState([]);
  const [input, setInput] = useState("");
  const [patientId, setPatientId] = useState("");
  const [mode, setMode] = useState("registration");
  const [showNotification, setShowNotification] = useState(false);
  const [showDashboard, setShowDashboard] = useState(false);

  useEffect(() => {
    // Initial greeting
    const initialMessage =
      mode === "monitor"
        ? {
            role: "assistant",
            content:
              "Welcome to the ED patient monitoring system! Please enter your patient ID to start tracking your condition.",
          }
        : {
            role: "assistant",
            content:
              "Hello! I'm your emergency department assistant. How can I help you today?",
          };
    setConversation([initialMessage]);
  }, [mode]);

  const sendMessage = async () => {
    if (input.trim() === "") return;

    const newMessage = { role: "user", content: input };
    setConversation([...conversation, newMessage]);
    setInput("");

    try {
      const endpoint = mode === "monitor" ? "/monitor_patient" : "/chat";
      const response = await axios.post(`http://localhost:8000${endpoint}`, {
        messages: [...conversation, newMessage],
        patient_id: patientId,
      });

      if (mode === "monitor" && response.data.reset_conversation) {
        setConversation([
          { role: "assistant", content: response.data.response },
        ]);
        setShowNotification(true);
      } else if (mode === "registration" && response.data.info_complete) {
        setConversation([
          { role: "assistant", content: response.data.response },
        ]);
        setShowNotification(true);
      } else {
        setConversation([
          ...conversation,
          newMessage,
          { role: "assistant", content: response.data.response },
        ]);
      }

      if (response.data.patient_id) {
        setPatientId(response.data.patient_id);
      }
    } catch (error) {
      console.error("Error:", error);
      setConversation([
        ...conversation,
        newMessage,
        {
          role: "assistant",
          content: "I'm sorry, there was an error processing your request.",
        },
      ]);
    }
  };

  const handleModeChange = (e) => {
    setMode(e.target.value);
    setConversation([]);
    setPatientId("");
    setShowNotification(false);
    setShowDashboard(false);
  };

  const handleViewDashboard = () => {
    if (patientId) {
      setShowDashboard(true);
    }
  };

  return (
    <div className="container mx-auto p-4">
      <div className="relative h-16 mb-6">
        <h1 className="text-3xl font-bold absolute left-0 top-1/2 transform -translate-y-1/2">
          Emergency Department Assistant
        </h1>
      </div>
      <div className="mb-4 -translate-y-1/3">
        <select
          value={mode}
          onChange={handleModeChange}
          className="px-4 py-2 rounded border text-lg"
        >
          <option value="registration">Registration & Triage Mode 🤖</option>
          <option value="monitor">Monitoring Mode 🩺 </option>
          <option value="dashboard">Patient Dashboard 📋</option>
        </select>
      </div>
      {mode === "dashboard" ? (
        <>
          <input
            type="text"
            value={patientId}
            onChange={(e) => setPatientId(e.target.value)}
            placeholder="Enter Patient ID"
            className="mb-4 px-4 py-2 border rounded"
          />
          <button
            onClick={handleViewDashboard}
            className="ml-2 px-4 py-2 bg-[rgb(61,54,170)] text-white rounded hover:bg-[rgb(51,44,160)]"
          >
            View Dashboard
          </button>
          {showDashboard && <PatientDashboard patientId={patientId} />}
        </>
      ) : (
        <>
          {patientId && <p className="mb-2">Patient ID: {patientId}</p>}
          <ChatComponent
            conversation={conversation}
            sendMessage={sendMessage}
            input={input}
            setInput={setInput}
            mode={mode}
          />
          <Notification
            message={
              mode === "monitor"
                ? "Patient status updated"
                : "Patient information collected"
            }
            isVisible={showNotification}
            onClose={() => setShowNotification(false)}
            mode={mode}
          />
        </>
      )}
    </div>
  );
};

export default App;
