import React, { useState, useRef, useEffect } from "react";
import axios from "axios";

const VoiceInputComponent = ({ onTranscription, mode }) => {
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const streamRef = useRef(null);
  const animationRef = useRef(null);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
      }
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
      if (audioContextRef.current) {
        audioContextRef.current.close();
      }
    };
  }, []);

  // Audio level monitoring for visual feedback
  const monitorAudioLevel = () => {
    if (analyserRef.current) {
      const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount);
      analyserRef.current.getByteFrequencyData(dataArray);

      const average =
        dataArray.reduce((sum, value) => sum + value, 0) / dataArray.length;
      setAudioLevel(average / 255); // Normalize to 0-1

      if (isRecording) {
        animationRef.current = requestAnimationFrame(monitorAudioLevel);
      }
    }
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          sampleRate: 44100,
        },
      });

      streamRef.current = stream;

      // Set up audio context for level monitoring
      audioContextRef.current = new (window.AudioContext ||
        window.webkitAudioContext)();
      analyserRef.current = audioContextRef.current.createAnalyser();
      const source = audioContextRef.current.createMediaStreamSource(stream);
      source.connect(analyserRef.current);
      analyserRef.current.fftSize = 256;

      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: "audio/webm;codecs=opus",
      });

      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, {
          type: "audio/webm",
        });
        await transcribeAudio(audioBlob);

        // Cleanup
        if (streamRef.current) {
          streamRef.current.getTracks().forEach((track) => track.stop());
        }
        if (audioContextRef.current) {
          audioContextRef.current.close();
        }
      };

      mediaRecorder.start();
      setIsRecording(true);
      monitorAudioLevel();
    } catch (error) {
      console.error("Error starting recording:", error);
      alert("Error accessing microphone. Please check permissions.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      setIsProcessing(true);
      setAudioLevel(0);

      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    }
  };

  const transcribeAudio = async (audioBlob) => {
    try {
      const formData = new FormData();
      formData.append("file", audioBlob, "recording.webm");

      const response = await axios.post(
        "http://localhost:8000/transcribe",
        formData,
        {
          headers: {
            "Content-Type": "multipart/form-data",
          },
        }
      );

      const transcription = response.data.transcription;
      onTranscription(transcription);
    } catch (error) {
      console.error("Error transcribing audio:", error);
      alert("Error transcribing audio. Please try again.");
    } finally {
      setIsProcessing(false);
    }
  };

  const toggleRecording = () => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  const getRecordButtonStyle = () => {
    const baseStyle =
      "relative w-12 h-12 rounded-full transition-all duration-300 flex items-center justify-center";
    const modeColor =
      mode === "registration"
        ? "bg-blue-500 hover:bg-blue-600"
        : "bg-green-500 hover:bg-green-600";

    if (isProcessing) {
      return `${baseStyle} ${modeColor} animate-pulse cursor-not-allowed`;
    } else if (isRecording) {
      return `${baseStyle} bg-red-500 hover:bg-red-600 animate-pulse`;
    } else {
      return `${baseStyle} ${modeColor} hover:scale-110`;
    }
  };

  return (
    <div className="flex items-center">
      {/* Recording Button */}
      <button
        onClick={toggleRecording}
        disabled={isProcessing}
        className={getRecordButtonStyle()}
        title={
          isRecording
            ? "Stop recording"
            : isProcessing
            ? "Processing..."
            : "Start recording"
        }
      >
        {/* Audio level visualization */}
        {isRecording && (
          <div
            className="absolute inset-0 rounded-full border-4 border-white opacity-60"
            style={{
              transform: `scale(${1 + audioLevel * 0.5})`,
              transition: "transform 0.1s ease-out",
            }}
          />
        )}

        <svg
          className="w-6 h-6 text-white relative z-10"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          {isProcessing ? (
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          ) : isRecording ? (
            <rect
              x="9"
              y="9"
              width="6"
              height="6"
              strokeWidth={2}
              fill="currentColor"
            />
          ) : (
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"
            />
          )}
        </svg>
      </button>
    </div>
  );
};

// Voice Output Component for TTS toggle
const VoiceOutputComponent = ({ mode }) => {
  const [isSpeechEnabled, setIsSpeechEnabled] = useState(false);

  const speakText = async (text) => {
    if (!isSpeechEnabled || !text) return;

    try {
      const response = await axios.post(
        "http://localhost:8000/text-to-speech",
        {
          text: text,
        }
      );

      const audioData = response.data.audio;
      const audioBlob = new Blob(
        [Uint8Array.from(atob(audioData), (c) => c.charCodeAt(0))],
        { type: "audio/mpeg" }
      );

      const audioUrl = URL.createObjectURL(audioBlob);
      const audio = new Audio(audioUrl);

      audio.onended = () => {
        URL.revokeObjectURL(audioUrl);
      };

      await audio.play();
    } catch (error) {
      console.error("Error playing speech:", error);
    }
  };

  // Expose speakText function to parent component
  useEffect(() => {
    if (window.voiceComponent) {
      window.voiceComponent.speakText = speakText;
    } else {
      window.voiceComponent = { speakText };
    }
  }, [isSpeechEnabled]);

  const getSpeechButtonStyle = () => {
    const baseStyle =
      "w-12 h-12 rounded-full transition-all duration-300 flex items-center justify-center";
    const modeColor =
      mode === "registration"
        ? "bg-blue-500 hover:bg-blue-600"
        : "bg-green-500 hover:bg-green-600";

    if (isSpeechEnabled) {
      return `${baseStyle} ${modeColor} hover:scale-110`;
    } else {
      return `${baseStyle} bg-gray-400 hover:bg-gray-500 hover:scale-110`;
    }
  };

  return (
    <button
      onClick={() => setIsSpeechEnabled(!isSpeechEnabled)}
      className={getSpeechButtonStyle()}
      title={
        isSpeechEnabled ? "Disable voice responses" : "Enable voice responses"
      }
    >
      <img
        src="/voice-output.png"
        alt={isSpeechEnabled ? "Voice output enabled" : "Voice output disabled"}
        className="w-6 h-6"
        style={{ filter: "brightness(0) invert(1)" }} // Makes the icon white
      />
    </button>
  );
};

export { VoiceInputComponent, VoiceOutputComponent };
