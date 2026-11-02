import { CfnResource, Names, type IAspect } from "aws-cdk-lib";
import type { IConstruct } from "constructs";
import { ENVIRONMENT_FUNCTION_PREFIX, ENVIRONMENT_IAM_PATH } from "./trust.ts";

/** Lambda's limit on a function name. */
const FUNCTION_NAME_LENGTH = 64;

/**
 * Puts every role and instance profile under the environment's IAM path and
 * names every function with the environment's prefix, including those CDK
 * creates internally, so the access stack's permissions can name them all.
 */
export class EnvironmentIdentities implements IAspect {
  visit(node: IConstruct): void {
    if (!(node instanceof CfnResource)) return;
    switch (node.cfnResourceType) {
      case "AWS::IAM::Role":
      case "AWS::IAM::InstanceProfile":
        node.addPropertyOverride("Path", ENVIRONMENT_IAM_PATH);
        break;
      case "AWS::Lambda::Function":
        node.addPropertyOverride("FunctionName", environmentFunctionName(node));
        break;
    }
  }
}

/** The stable name of the function *node* defines, unique within its app. */
function environmentFunctionName(node: IConstruct): string {
  return `${ENVIRONMENT_FUNCTION_PREFIX}${Names.uniqueResourceName(node, {
    maxLength: FUNCTION_NAME_LENGTH - ENVIRONMENT_FUNCTION_PREFIX.length,
  })}`;
}
