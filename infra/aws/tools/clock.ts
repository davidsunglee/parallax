/** Time as the rollout tools read and spend it. */
export interface Clock {
  /** Milliseconds since the epoch, comparable with the API's timestamps. */
  wall(): number;
  /** Milliseconds on a clock that never goes back, for deadlines. */
  monotonic(): number;
  sleep(milliseconds: number): void;
}

export const systemClock: Clock = {
  wall: () => Date.now(),
  monotonic: () => performance.now(),
  sleep: (milliseconds) => {
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, milliseconds);
  },
};
