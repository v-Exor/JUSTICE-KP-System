"use client";

import axios from "axios";
import { useRef, useState } from "react";

type TranscriptSegment = {
  speaker: string;
  start: number;
  end: number;
  text: string;
  confidence?: number | null;
};

type UploadResponse = {
  provider?: string;
  recording_type?: string;
  expected_speakers?: number;
  asr_confidence?: number | null;
  diarization_quality?: number | null;
  accuracy_metrics?: Record<string, unknown>;
  transcript: TranscriptSegment[];
  warnings?: string[];
};

type SaveTranscriptResponse = {
  learned_corrections?: number;
  accuracy_metrics?: Record<string, unknown>;
};

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

function formatTranscript(segments: TranscriptSegment[]) {
  return segments
    .map((segment) => `${segment.speaker}: ${segment.text}`)
    .join("\n");
}

export default function Recorder() {
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);

  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [speakerCount, setSpeakerCount] = useState("3");
  const [statusMessage, setStatusMessage] = useState("Ready to record.");
  const [errorMessage, setErrorMessage] = useState("");
  const [warningMessage, setWarningMessage] = useState("");
  const [uploadMetrics, setUploadMetrics] = useState<Pick<
    UploadResponse,
    "provider" | "recording_type" | "expected_speakers" | "asr_confidence" | "diarization_quality" | "accuracy_metrics"
  > | null>(null);

  const startRecording = async () => {
    setErrorMessage("");
    setWarningMessage("");

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      streamRef.current = stream;
      audioChunksRef.current = [];

      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";
      const recorder = new MediaRecorder(stream, {
        audioBitsPerSecond: 128000,
        mimeType,
      });
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = handleRecordingStop;
      recorder.start();

      setIsRecording(true);
      setStatusMessage("Recording hearing audio...");
    } catch {
      setErrorMessage("Microphone access was denied or unavailable.");
      setStatusMessage("Ready to record.");
    }
  };

  const stopRecording = () => {
    if (!mediaRecorderRef.current || mediaRecorderRef.current.state === "inactive") {
      return;
    }

    mediaRecorderRef.current.stop();
    setIsRecording(false);
    setIsProcessing(true);
    setStatusMessage("Uploading audio and generating transcript...");

    streamRef.current?.getTracks().forEach((track) => track.stop());
  };

  const handleRecordingStop = async () => {
    const audioBlob = new Blob(audioChunksRef.current, { type: "audio/webm" });
    const formData = new FormData();
    formData.append("file", audioBlob, `justice-kp-${Date.now()}.webm`);
    formData.append("speaker_count", speakerCount);
    formData.append("recording_type", speakerCount === "2" ? "blotter_case" : "blotter_hearing");

    try {
      const response = await axios.post<UploadResponse>(
        `${API_BASE_URL}/upload`,
        formData,
        { headers: { "Content-Type": "multipart/form-data" } }
      );

      setSegments(response.data.transcript);
      setTranscript(formatTranscript(response.data.transcript));
      setUploadMetrics({
        provider: response.data.provider,
        recording_type: response.data.recording_type,
        expected_speakers: response.data.expected_speakers,
        asr_confidence: response.data.asr_confidence,
        diarization_quality: response.data.diarization_quality,
        accuracy_metrics: response.data.accuracy_metrics,
      });
      setWarningMessage(response.data.warnings?.join(" ") ?? "");
      setStatusMessage(
        response.data.transcript.length
          ? "Transcript ready for review and editing."
          : "No speech was detected. Try recording again closer to the microphone."
      );
    } catch (error) {
      const detail = axios.isAxiosError(error)
        ? error.response?.data?.detail
        : undefined;
      setErrorMessage(
        detail ?? "Transcription failed. Check that the FastAPI backend is running."
      );
      setStatusMessage("Ready to record.");
    } finally {
      setIsProcessing(false);
      audioChunksRef.current = [];
    }
  };

  const saveTranscript = async () => {
    if (!transcript.trim()) {
      setErrorMessage("Transcript is empty. Record or enter transcript text first.");
      return;
    }

    setIsSaving(true);
    setErrorMessage("");

    try {
      const response = await axios.post<SaveTranscriptResponse>(`${API_BASE_URL}/save-transcript`, {
        content: transcript,
        segments,
        provider: uploadMetrics?.provider ?? "",
        recording_type: uploadMetrics?.recording_type ?? "",
        expected_speakers: uploadMetrics?.expected_speakers,
        asr_confidence: uploadMetrics?.asr_confidence,
        diarization_quality: uploadMetrics?.diarization_quality,
        accuracy_metrics: uploadMetrics?.accuracy_metrics ?? {},
      });
      const learnedCount = response.data.learned_corrections ?? 0;
      setStatusMessage(
        learnedCount
          ? `Edited transcript saved. Learned ${learnedCount} correction${learnedCount === 1 ? "" : "s"} for future recordings.`
          : "Edited transcript saved."
      );
    } catch {
      setErrorMessage("Saving failed. Check the backend connection and try again.");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <main className="min-h-screen bg-gray-100 px-4 py-8 text-black sm:px-6 lg:px-8">
      <section className="mx-auto max-w-5xl">
        <div className="mb-6 border-b border-gray-300 pb-5">
          <p className="text-sm font-semibold uppercase tracking-wide text-blue-700">
            Katarungang Pambarangay Hearing Recorder
          </p>
          <h1 className="mt-2 text-3xl font-bold text-gray-950 sm:text-4xl">
            JUSTICE-KP Phase 1: ASR and Speaker Transcript
          </h1>
        </div>

        <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
          <aside className="rounded-lg border border-gray-300 bg-white p-5 shadow-sm">
            <h2 className="text-lg font-semibold text-gray-950">Recording Controls</h2>
            <p className="mt-2 text-sm leading-6 text-gray-600">
              Record browser microphone audio, stop when done, then review the editable
              speaker transcript.
            </p>

            <div className="mt-5 flex flex-col gap-3">
              <label className="text-sm font-semibold text-gray-700" htmlFor="speaker-count">
                Recording Mode
              </label>
              <select
                id="speaker-count"
                value={speakerCount}
                onChange={(event) => setSpeakerCount(event.target.value)}
                disabled={isRecording || isProcessing}
                className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-950 outline-none focus:border-blue-700 focus:ring-2 focus:ring-blue-100 disabled:bg-gray-100"
              >
                <option value="2">Blotter Recording (2 speakers)</option>
                <option value="3">Hearing Recording (3 speakers)</option>
              </select>

              <button
                onClick={startRecording}
                disabled={isRecording || isProcessing}
                className="rounded-md bg-blue-700 px-4 py-3 text-sm font-semibold text-white transition hover:bg-blue-800 disabled:cursor-not-allowed disabled:bg-gray-400"
              >
                Start Recording
              </button>
              <button
                onClick={stopRecording}
                disabled={!isRecording}
                className="rounded-md bg-gray-950 px-4 py-3 text-sm font-semibold text-white transition hover:bg-black disabled:cursor-not-allowed disabled:bg-gray-400"
              >
                Stop Recording
              </button>
            </div>

            <div className="mt-5 rounded-md border border-gray-200 bg-gray-50 p-4">
              <p className="text-xs font-semibold uppercase text-gray-500">Status</p>
              <p className="mt-1 text-sm text-gray-900">
                {isProcessing ? "Processing audio. This may take a few minutes." : statusMessage}
              </p>
              {isRecording && (
                <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-gray-200">
                  <div className="h-full w-2/3 animate-pulse rounded-full bg-blue-700" />
                </div>
              )}
            </div>

            {errorMessage && (
              <p className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                {errorMessage}
              </p>
            )}

            {warningMessage && (
              <p className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                {warningMessage}
              </p>
            )}
          </aside>

          <section className="rounded-lg border border-gray-300 bg-white p-5 shadow-sm">
            <div className="flex flex-col gap-3 border-b border-gray-200 pb-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-lg font-semibold text-gray-950">Editable Transcript</h2>
                <p className="mt-1 text-sm text-gray-600">
                  Speaker labels are limited to Speaker 1, Speaker 2, and Speaker 3.
                </p>
              </div>
              <button
                onClick={saveTranscript}
                disabled={isSaving || isProcessing || !transcript.trim()}
                className="rounded-md border border-blue-700 bg-white px-4 py-2 text-sm font-semibold text-blue-700 transition hover:bg-blue-50 disabled:cursor-not-allowed disabled:border-gray-300 disabled:text-gray-400"
              >
                {isSaving ? "Saving..." : "Save Transcript"}
              </button>
            </div>

            <textarea
              value={transcript}
              onChange={(event) => setTranscript(event.target.value)}
              placeholder="Recorded transcript will appear here..."
              className="mt-4 h-[520px] w-full resize-none rounded-md border border-gray-300 bg-gray-50 p-4 font-mono text-sm leading-6 text-gray-950 outline-none transition focus:border-blue-700 focus:bg-white focus:ring-2 focus:ring-blue-100"
            />
          </section>
        </div>
      </section>
    </main>
  );
}
