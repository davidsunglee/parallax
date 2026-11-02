import { App } from "aws-cdk-lib";
import { defineStacks } from "../src/stacks.ts";

const app = new App();
defineStacks(app);
app.synth();
