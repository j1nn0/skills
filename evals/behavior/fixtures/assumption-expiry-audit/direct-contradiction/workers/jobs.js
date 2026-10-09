import { Queue } from "bullmq";
import IORedis from "ioredis";

const connection = new IORedis(process.env.REDIS_URL);
const queue = new Queue("background-jobs", { connection });

export function enqueue(job) {
  return queue.add("job", job);
}
