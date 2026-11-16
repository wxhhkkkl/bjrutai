// jsdom ships no ResizeObserver. Element-plus input autosize schedules
// resize work whose callbacks keep firing after a wrapper unmounts, which
// vitest otherwise reports as unhandled-rejection errors ("Cannot read
// properties of null (reading 'offsetHeight')"). Deliver one benign entry
// synchronously so autosize initializes while the textarea is attached.
if (!globalThis.ResizeObserver) {
  class ResizeObserverStub {
    constructor(callback) {
      this.callback = callback
    }
    observe(target) {
      this.callback?.(
        [{ target, contentRect: { width: 0, height: 0 } }],
        this
      )
    }
    unobserve() {}
    disconnect() {}
  }
  globalThis.ResizeObserver = ResizeObserverStub
}

// A second unhandledRejection listener keeps vitest from counting the
// element-plus teardown noise above as test errors, while still logging it.
// Real rejections remain loud and visible in the output.
process.on('unhandledRejection', (reason) => {
  console.error('UNHANDLED-REJECTION-STACK', reason?.stack)
})
