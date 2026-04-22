Blender's main thread is single-threaded. Addon code (hooks, operators, timers) all executes on the main thread sequentially.
