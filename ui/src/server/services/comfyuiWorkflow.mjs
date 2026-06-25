export function buildSimpleTextToImageWorkflow(args = {}) {
  return {
    "1": {
      class_type: "CheckpointLoaderSimple",
      inputs: {
        ckpt_name: args.checkpointName
      }
    },
    "2": {
      class_type: "CLIPTextEncode",
      inputs: {
        text: args.prompt,
        clip: ["1", 1]
      }
    },
    "3": {
      class_type: "CLIPTextEncode",
      inputs: {
        text: args.negativePrompt || "",
        clip: ["1", 1]
      }
    },
    "4": {
      class_type: "EmptyLatentImage",
      inputs: {
        width: args.width || 1024,
        height: args.height || 1024,
        batch_size: 1
      }
    },
    "5": {
      class_type: "KSampler",
      inputs: {
        seed: args.seed,
        steps: args.steps || 28,
        cfg: args.cfg || 7,
        sampler_name: "euler",
        scheduler: "normal",
        denoise: 1,
        model: ["1", 0],
        positive: ["2", 0],
        negative: ["3", 0],
        latent_image: ["4", 0]
      }
    },
    "6": {
      class_type: "VAEDecode",
      inputs: {
        samples: ["5", 0],
        vae: ["1", 2]
      }
    },
    "7": {
      class_type: "SaveImage",
      inputs: {
        filename_prefix: args.filenamePrefix || "forge-art",
        images: ["6", 0]
      }
    }
  };
}
