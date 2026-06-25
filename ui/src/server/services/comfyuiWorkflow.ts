export type SimpleTextToImageWorkflowArgs = {
  prompt: string;
  negativePrompt: string;
  width: number;
  height: number;
  steps: number;
  cfg: number;
  seed: number;
  checkpointName: string;
  filenamePrefix: string;
};

export type ComfyUiWorkflow = Record<string, {
  class_type: string;
  inputs: Record<string, unknown>;
}>;

export function buildSimpleTextToImageWorkflow(args: SimpleTextToImageWorkflowArgs): ComfyUiWorkflow {
  return {
    "1": {
      class_type: "CheckpointLoaderSimple",
      inputs: {
        ckpt_name: args.checkpointName,
      },
    },
    "2": {
      class_type: "CLIPTextEncode",
      inputs: {
        text: args.prompt,
        clip: ["1", 1],
      },
    },
    "3": {
      class_type: "CLIPTextEncode",
      inputs: {
        text: args.negativePrompt,
        clip: ["1", 1],
      },
    },
    "4": {
      class_type: "EmptyLatentImage",
      inputs: {
        width: args.width,
        height: args.height,
        batch_size: 1,
      },
    },
    "5": {
      class_type: "KSampler",
      inputs: {
        seed: args.seed,
        steps: args.steps,
        cfg: args.cfg,
        sampler_name: "euler",
        scheduler: "normal",
        denoise: 1,
        model: ["1", 0],
        positive: ["2", 0],
        negative: ["3", 0],
        latent_image: ["4", 0],
      },
    },
    "6": {
      class_type: "VAEDecode",
      inputs: {
        samples: ["5", 0],
        vae: ["1", 2],
      },
    },
    "7": {
      class_type: "SaveImage",
      inputs: {
        filename_prefix: args.filenamePrefix,
        images: ["6", 0],
      },
    },
  };
}
