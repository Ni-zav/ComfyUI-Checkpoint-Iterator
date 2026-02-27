import folder_paths
import comfy.sd

class CheckpointLoaderIterator:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": { 
            "batch_index": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
        }}
    
    RETURN_TYPES = ("MODEL", "CLIP", "VAE", "STRING")
    RETURN_NAMES = ("MODEL", "CLIP", "VAE", "CKPT_NAME")
    FUNCTION = "load_checkpoint"
    CATEGORY = "loaders"

    def load_checkpoint(self, batch_index):
        checkpoints = folder_paths.get_filename_list("checkpoints")
        if not checkpoints:
            raise ValueError("No checkpoints found.")
        
        # Calculate the index to use based on batch_index
        index = batch_index % len(checkpoints)
        ckpt_name = checkpoints[index]
        
        ckpt_path = folder_paths.get_full_path_or_raise("checkpoints", ckpt_name)
        out = comfy.sd.load_checkpoint_guess_config(ckpt_path, output_vae=True, output_clip=True, embedding_directory=folder_paths.get_folder_paths("embeddings"))
        
        return (out[0], out[1], out[2], ckpt_name)

    @classmethod
    def IS_CHANGED(s, batch_index):
        # We want to re-evaluate on every execution if the batch_index changes
        return batch_index

NODE_CLASS_MAPPINGS = {
    "CheckpointLoaderIterator": CheckpointLoaderIterator
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "CheckpointLoaderIterator": "Checkpoint Loader Iterator"
}
