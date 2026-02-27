# ComfyUI Checkpoint Iterator

A custom node for ComfyUI that allows you to easily iterate through all of your downloaded checkpoints sequentially or dynamically. This is extremely useful for testing prompts or settings against a large batch of different models without manually changing the checkpoint loader node each time.

## Installation

1. Navigate to your ComfyUI `custom_nodes` directory.
   ```bash
   cd ComfyUI/custom_nodes
   ```
2. Clone this repository (or copy the folder into the `custom_nodes` directory).
   ```bash
   git clone https://github.com/yourusername/ComfyUI-Checkpoint-Iterator.git
   ```
3. Restart ComfyUI.

## Usage

1. In the ComfyUI canvas, right-click and go to **Add Node -> loaders -> Checkpoint Loader Iterator**.
2. Right-click the newly added node and select **Convert batch_index to input**.
3. Add a **Primitive Node** (Add Node -> utils -> Primitive).
4. Connect the Primitive node to the `batch_index` input of the Checkpoint Loader.
5. Select the Primitive node in the UI and set its `control_after_generate` behavior from `fixed` to **`increment`**.
6. Set the **Batch count** in the ComfyUI main control panel to the number of checkpoints you want to test (e.g., 10, 30).
7. Click **Queue Prompt**.

## How it works

For each image generated in the batch queue, the Primitive node will increment the batch index by 1. The custom node calculates `index % total_checkpoints` to select the corresponding checkpoint from your models folder and loads it. 

### Outputs
*   **MODEL, CLIP, VAE:** The standard outputs required for ComfyUI workflows.
*   **CKPT_NAME:** (String) The exact filename of the checkpoint currently loaded. You can route this string into a custom "Save Image" node to automatically include the model name in your generated image filenames for easy comparison.

## License

MIT License
