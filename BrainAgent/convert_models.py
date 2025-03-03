#!/usr/bin/env python3
import os
import tensorflow as tf
import tensorflow_hub as hub

def convert_movenet_to_tflite(model_name="lightning", output_dir="models"):
    """
    Convert MoveNet model from TF Hub to TFLite format
    
    Args:
        model_name: Either "lightning" or "thunder"
        output_dir: Directory to save the TFLite model
    
    Returns:
        Path to the converted TFLite model
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Define model URL based on model_name
    if model_name == "thunder":
        model_url = "https://tfhub.dev/google/movenet/singlepose/thunder/4"
        tflite_filename = "movenet_thunder.tflite"
    else:
        model_url = "https://tfhub.dev/google/movenet/singlepose/lightning/4"
        tflite_filename = "movenet_lightning.tflite"
    
    output_path = os.path.join(output_dir, tflite_filename)
    
    # Check if model already exists
    if os.path.exists(output_path):
        print(f"TFLite model already exists at {output_path}")
        return output_path
    
    print(f"Loading MoveNet {model_name} model from TF Hub...")
    model = hub.load(model_url)
    
    # Get concrete function
    concrete_func = model.signatures['serving_default']
    
    # Convert the model to TFLite
    print("Converting model to TFLite format...")
    converter = tf.lite.TFLiteConverter.from_concrete_functions([concrete_func])
    
    # Set optimization flags
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    converter.target_spec.supported_types = [tf.float16]
    
    # Convert the model
    tflite_model = converter.convert()
    
    # Save the model
    with open(output_path, 'wb') as f:
        f.write(tflite_model)
    
    print(f"Model converted and saved to {output_path}")
    return output_path

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Convert MoveNet to TFLite')
    parser.add_argument('--model', type=str, default='lightning', 
                        choices=['lightning', 'thunder'],
                        help='MoveNet model type to convert')
    parser.add_argument('--output', type=str, default='models',
                        help='Output directory for the TFLite model')
    
    args = parser.parse_args()
    
    convert_movenet_to_tflite(args.model, args.output)