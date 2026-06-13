/**
 * Voice client — MediaRecorder + WebRTC VAD integration.
 * Captures audio from the microphone, buffers it while speech is detected,
 * then fires an `onAudioReady` callback with the recorded Blob.
 */

export interface VoiceClientOptions {
  /** Called when speech has been captured and recording has stopped. */
  onAudioReady: (blob: Blob, mimeType: string) => void;
  /** Called when the client status changes. */
  onStatusChange?: (status: VoiceStatus) => void;
  /** Called on error. */
  onError?: (err: Error) => void;
  /** Silence threshold in ms before auto-stopping (default 1500). */
  silenceThresholdMs?: number;
  /** Preferred audio sample rate (default 16000 for Whisper). */
  sampleRate?: number;
}

export type VoiceStatus =
  | "idle"
  | "requesting_permission"
  | "listening"
  | "recording"
  | "processing"
  | "error";

const PREFERRED_MIME_TYPES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
  "audio/ogg",
  "audio/mp4",
];

function getSupportedMimeType(): string {
  for (const type of PREFERRED_MIME_TYPES) {
    if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(type)) {
      return type;
    }
  }
  return "";
}

export class VoiceClient {
  private options: Required<VoiceClientOptions>;
  private stream: MediaStream | null = null;
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private silenceTimer: ReturnType<typeof setTimeout> | null = null;
  private status: VoiceStatus = "idle";
  private mimeType: string;

  private audioContext: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private voiceVolumeNode: MediaStreamAudioSourceNode | null = null;
  private volumeInterval: ReturnType<typeof setInterval> | null = null;
  private hasSpoken = false;
  private maxDurationTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(options: VoiceClientOptions) {
    this.options = {
      silenceThresholdMs: 1500,
      sampleRate: 16000,
      onStatusChange: () => undefined,
      onError: () => undefined,
      ...options,
    };
    this.mimeType = getSupportedMimeType();
  }

  // ── Public API ────────────────────────────────────────────────────────

  /** Request microphone access and start listening. */
  async start(): Promise<void> {
    if (this.status !== "idle") return;
    this._setStatus("requesting_permission");

    try {
      const hasActiveTracks = this.stream && this.stream.getTracks().some(t => t.readyState === 'live');
      if (!hasActiveTracks) {
        this.stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            sampleRate:   this.options.sampleRate,
            channelCount: 1,
            echoCancellation: true,
            noiseSuppression: true,
          },
        });
      }

      this._setStatus("listening");
      this._startRecording();
    } catch (err) {
      this._setStatus("error");
      this.options.onError(
        err instanceof Error ? err : new Error(`Microphone initialization failed: ${String(err)}`)
      );
    }
  }

  /** Stop recording and emit the audio. */
  stop(): void {
    if (this.silenceTimer) {
      clearTimeout(this.silenceTimer);
      this.silenceTimer = null;
    }
    this._stopRecording();
  }

  /** Initialize/resume AudioContext synchronously under user gesture. */
  initAudioContext(): void {
    if (typeof window === "undefined") return;
    try {
      if (!this.audioContext) {
        const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
        this.audioContext = new AudioContextClass();
        console.log("[VoiceClient] AudioContext initialized synchronously.");
      }
      if (this.audioContext && this.audioContext.state === "suspended") {
        this.audioContext.resume().then(() => {
          console.log("[VoiceClient] AudioContext resumed successfully.");
        }).catch(err => {
          console.warn("[VoiceClient] Failed to resume AudioContext:", err);
        });
      }
    } catch (e) {
      console.warn("[VoiceClient] Failed to initialize AudioContext:", e);
    }
  }

  /** Release all resources. */
  destroy(): void {
    this.stop();
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    if (this.audioContext && this.audioContext.state !== "closed") {
      this.audioContext.close().catch(err => {
        console.warn("[VoiceClient] Error closing AudioContext during destroy:", err);
      });
      this.audioContext = null;
    }
    this._setStatus("idle");
  }

  get currentStatus(): VoiceStatus {
    return this.status;
  }

  // ── Internal helpers ─────────────────────────────────────────────────

  private _startRecording(): void {
    if (!this.stream) return;

    this.chunks = [];
    const options: MediaRecorderOptions = {};
    if (this.mimeType) {
      options.mimeType = this.mimeType;
    }
    this.recorder = new MediaRecorder(this.stream, options);

    if (this.recorder.mimeType) {
      this.mimeType = this.recorder.mimeType;
    }

    this.recorder.ondataavailable = (e: BlobEvent) => {
      if (e.data.size > 0) this.chunks.push(e.data);
    };

    this.recorder.onstop = () => {
      if (this.chunks.length === 0) {
        this._setStatus("idle");
        return;
      }
      this._setStatus("processing");
      const blob = new Blob(this.chunks, { type: this.mimeType });
      this.chunks = [];
      this._setStatus("idle");
      this.options.onAudioReady(blob, this.mimeType);
    };

    this.recorder.start(100); // collect data every 100ms
    this._setStatus("recording");

    this.hasSpoken = false;

    // Set up Web Audio API analyser for volume-based VAD
    try {
      if (!this.audioContext) {
        const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
        this.audioContext = new AudioContextClass();
      }
      
      if (this.audioContext.state === "suspended") {
        this.audioContext.resume().catch(err => {
          console.warn("[VoiceClient] Error resuming AudioContext:", err);
        });
      }

      this.voiceVolumeNode = this.audioContext.createMediaStreamSource(this.stream);
      
      if (!this.analyser) {
        this.analyser = this.audioContext.createAnalyser();
        this.analyser.fftSize = 512;
      }
      this.voiceVolumeNode.connect(this.analyser);

      const bufferLength = this.analyser.frequencyBinCount;
      const dataArray = new Uint8Array(bufferLength);

      const startTime = Date.now();
      this.volumeInterval = setInterval(() => {
        if (!this.analyser) return;
        this.analyser.getByteTimeDomainData(dataArray);

        let sum = 0;
        for (let i = 0; i < bufferLength; i++) {
          const v = (dataArray[i] - 128) / 128;
          sum += v * v;
        }
        const rms = Math.sqrt(sum / bufferLength);

        // Ignore VAD checks during the first 500ms to avoid mic startup pop/click noise
        if (Date.now() - startTime < 500) {
          return;
        }

        // Speech volume threshold (0.015)
        if (rms > 0.015) {
          if (!this.hasSpoken) {
            this.hasSpoken = true;
            console.log("[VoiceClient] Speech detected! Starting VAD auto-stop loop.");
          }
          this._resetSilenceTimer();
        }
      }, 100);
    } catch (e) {
      console.warn("[VoiceClient] Could not initialize Web Audio analyzer:", e);
    }

    // Safety timeout: stop recording after 60 seconds of continuous session
    this.maxDurationTimer = setTimeout(() => {
      console.log("[VoiceClient] Max duration reached - stopping recording");
      this.stop();
    }, 60000);

    // Initialise silence timer check
    this._resetSilenceTimer();
  }

  private _stopRecording(): void {
    if (this.volumeInterval) {
      clearInterval(this.volumeInterval);
      this.volumeInterval = null;
    }
    if (this.voiceVolumeNode) {
      this.voiceVolumeNode.disconnect();
      this.voiceVolumeNode = null;
    }
    if (this.analyser) {
      this.analyser.disconnect();
      this.analyser = null;
    }
    if (this.audioContext && this.audioContext.state === "running") {
      this.audioContext.suspend().catch(err => {
        console.warn("[VoiceClient] Error suspending AudioContext:", err);
      });
    }
    if (this.maxDurationTimer) {
      clearTimeout(this.maxDurationTimer);
      this.maxDurationTimer = null;
    }

    if (this.recorder && this.recorder.state !== "inactive") {
      this.recorder.stop();
    }

    if (this.stream) {
      this.stream.getTracks().forEach((track) => track.stop());
      this.stream = null;
    }
  }

  private _resetSilenceTimer(): void {
    if (this.silenceTimer) clearTimeout(this.silenceTimer);
    this.silenceTimer = setTimeout(() => {
      if (this.hasSpoken) {
        console.log("[VoiceClient] Silence timeout - stopping recording");
        this.stop();
      } else {
        // Keep listening as user has not spoken yet
        this._resetSilenceTimer();
      }
    }, this.options.silenceThresholdMs);
  }

  private _setStatus(s: VoiceStatus): void {
    this.status = s;
    this.options.onStatusChange(s);
  }
}

// ── Utility: encode blob to base64 ────────────────────────────────────────

export function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const result = reader.result as string;
      // strip the data URL prefix: "data:<mime>;base64,"
      resolve(result.split(",")[1]);
    };
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}
