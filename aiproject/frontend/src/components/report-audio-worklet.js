class ReportAudioCapture extends AudioWorkletProcessor {
  process(inputs) {
    const samples = inputs[0]?.[0]
    if (samples?.length) this.port.postMessage(samples)
    return true
  }
}

registerProcessor('report-audio-capture', ReportAudioCapture)
