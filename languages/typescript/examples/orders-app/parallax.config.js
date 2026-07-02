// Sample-app Parallax generator config (spec §7). `parallax generate` reads this
// and materializes the `#parallax` barrel at `output`.
import { defineParallaxConfig } from "@parallax/typescript/config";

export default defineParallaxConfig({
  descriptors: ["./parallax/**/*.yaml"],
  output: "./.parallax/generated",
  importAlias: "#parallax",
});
