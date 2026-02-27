# ComfyUI Checkpoint Iterator

A custom node for ComfyUI that allows you to easily iterate through all of your downloaded checkpoints sequentially or dynamically. This is extremely useful for testing prompts or settings against a large batch of different models without manually changing the checkpoint loader node each time.

## Installation

1. Navigate to your ComfyUI `custom_nodes` directory.
   ```bash
   cd ComfyUI/custom_nodes
   ```
2. Clone this repository (or copy the folder into the `custom_nodes` directory).
   ```bash
   git clone https://github.com/Ni-zav/ComfyUI-Checkpoint-Iterator.git
   ```
3. Restart ComfyUI.

## Usage

1. In the ComfyUI canvas, right-click and go to **Add Node -> loaders -> Checkpoint Loader Iterator**.
2. Connect `MODEL`, `CLIP`, and `VAE` outputs into your normal pipeline (`KSampler`, encoders, etc.).
3. (Optional) Connect `CKPT_NAME` to your filename prefix so each saved image includes the model name.
4. Queue multiple prompts from the main queue controls.

### Iteration behavior

This node has no index input now. It advances automatically on each execution.

- 1st execution -> checkpoint 0
- 2nd execution -> checkpoint 1
- ...
- wraps with modulo when it reaches the end

### Memory behavior

Before loading the next checkpoint, the node unloads previous models and clears cache to reduce VRAM carry-over between checkpoints.

### Important note about "batch"

`KSampler` latent/image batch size is not the same as queue iteration count.
To iterate checkpoints, queue multiple executions (prompt queue), not just a larger sampler batch size.

## How it works

For each image generated in the batch queue, the Primitive node will increment the batch index by 1. The custom node calculates `index % total_checkpoints` to select the corresponding checkpoint from your models folder and loads it. 

### Outputs
*   **MODEL, CLIP, VAE:** The standard outputs required for ComfyUI workflows.
*   **CKPT_NAME:** (String) The exact filename of the checkpoint currently loaded. You can route this string into a custom "Save Image" node to automatically include the model name in your generated image filenames for easy comparison.

## License

MIT License
