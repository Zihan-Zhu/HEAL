import React, { useState, useEffect } from 'react';

const PatientDashboard = ({ patientId }) => {
  const [patientData, setPatientData] = useState({});

  useEffect(() => {
    const eventSource = new EventSource(`http://localhost:8000/dashboard/${patientId}`);

    eventSource.addEventListener("update", (e) => {
      console.log("Update event received:", e);
      try {
        const data = JSON.parse(e.data);
        console.log("Parsed data:", data);
        setPatientData(prevData => ({...prevData, ...data}));
      } catch (error) {
        console.error("Error parsing event data:", error);
      }
    });

    eventSource.onerror = (error) => {
      console.error('EventSource error:', error);
      eventSource.close();
    };

    return () => eventSource.close();
  }, [patientId]);

  const renderField = (label, value) => (
    <p><strong>{label}:</strong> {value || 'N/A'}</p>
  );

  const primarySurveyLabels = {
    A: 'Airway',
    B: 'Breathing',
    C: 'Circulation',
    D: 'Disability',
    E: 'Environment'
  };


  return (
    <div className="bg-white shadow-md rounded px-8 pt-6 pb-8 mb-4">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <h3 className="text-xl font-semibold mb-2 text-[rgb(61,54,170)]">Patient Information</h3>
          {renderField('Name', patientData.name)}
          {renderField('Age', patientData.age)}
          {renderField('Gender', patientData.gender)}
          {renderField('Presenting Problem', patientData.presenting_problem)}
          {renderField('Associated Symptoms', patientData.associated_symptoms)}
          <h4 className="text-base font-bold mt-3">Primary Survey</h4>
          {patientData.primary_survey && Object.entries(patientData.primary_survey).map(([key, value]) => (
            <p key={key}><strong>{primarySurveyLabels[key]}:</strong> {value || 'N/A'}</p>
          ))}
          <div className="mt-3">
            {renderField('Focused Assessment', patientData.focused_assessment)}
            {renderField('Pertinent History', patientData.pertinent_history)}
            {renderField('Red Flags', patientData.red_flags)}
          </div>
        </div>
        <div>
          <h3 className="text-xl font-semibold mb-2 text-[rgb(61,54,170)]">Monitoring Information</h3>
          {renderField('Re-triage Time', patientData.retriage_time)}
          {renderField('Condition Change', patientData.condition_change)}
          <h3 className="text-xl font-semibold mt-4 mb-2 text-[rgb(61,54,170)]">Triage Information</h3>
          {renderField('ATS Category', patientData.ats_category)}
          {renderField('Re-triage ATS Category', patientData.ats_category_retriage)}
        </div>
      </div>
    </div>
  );
};

export default PatientDashboard;