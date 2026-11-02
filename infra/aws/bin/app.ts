import { App } from "aws-cdk-lib";
import { defineEnvironment } from "../src/environment-stack.ts";

const app = new App();
defineEnvironment(app);
app.synth();
