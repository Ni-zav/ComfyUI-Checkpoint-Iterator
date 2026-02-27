import folder_paths
import comfy.sd
import gc

try:
    import comfy.model_management as model_management
except Exception:
    model_management = None

class CheckpointLoaderIterator:
    _auto_index = 0

    @classmethod
    def INPUT_TYPES(s):
        return {"required": {}}
    
    RETURN_TYPES = ("MODEL", "CLIP", "VAE", "STRING")
    RETURN_NAMES = ("MODEL", "CLIP", "VAE", "CKPT_NAME")
    FUNCTION = "load_checkpoint"
    CATEGORY = "loaders"

    def _release_previous_checkpoint(self):
        if model_management is None:
            gc.collect()
            return

        if hasattr(model_management, "unload_all_models"):
            model_management.unload_all_models()
        if hasattr(model_management, "soft_empty_cache"):
            model_management.soft_empty_cache()
        elif hasattr(model_management, "empty_cache"):
            model_management.empty_cache()
        gc.collect()

    def load_checkpoint(self):
        checkpoints = folder_paths.get_filename_list("checkpoints")
        if not checkpoints:
            raise ValueError("No checkpoints found.")

        index = CheckpointLoaderIterator._auto_index % len(checkpoints)
        CheckpointLoaderIterator._auto_index += 1

        ckpt_name = checkpoints[index]

        self._release_previous_checkpoint()

        ckpt_path = folder_paths.get_full_path_or_raise("checkpoints", ckpt_name)
        out = comfy.sd.load_checkpoint_guess_config(ckpt_path, output_vae=True, output_clip=True, embedding_directory=folder_paths.get_folder_paths("embeddings"))

        return (out[0], out[1], out[2], ckpt_name)

    @classmethod
    def IS_CHANGED(s):
        return float("NaN")

NODE_CLASS_MAPPINGS = {
    "CheckpointLoaderIterator": CheckpointLoaderIterator
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "CheckpointLoaderIterator": "Checkpoint Loader Iterator"
}
