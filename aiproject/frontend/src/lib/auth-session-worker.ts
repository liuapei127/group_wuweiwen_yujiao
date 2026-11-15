// Let the worker serialize session cookie changes across full page navigations.
let controllerReady: Promise<void> | undefined

export function prepareSessionWorker(): Promise<void> {
  const workers = navigator.serviceWorker
  if (!workers || workers.controller?.scriptURL === new URL('/ent-auth-worker.js', location.origin).href) {
    return Promise.resolve()
  }

  if (!controllerReady) {
    controllerReady = new Promise<void>(resolve => {
      const finish = () => {
        window.clearTimeout(timeout)
        workers.removeEventListener('controllerchange', onChange)
        resolve()
      }
      const onChange = () => {
        if (workers.controller?.scriptURL === new URL('/ent-auth-worker.js', location.origin).href) finish()
      }
      const timeout = window.setTimeout(finish, 3000)
      workers.addEventListener('controllerchange', onChange)
      void workers.register('/ent-auth-worker.js').then(onChange, finish)
    }).finally(() => { controllerReady = undefined })
  }
  return controllerReady
}
