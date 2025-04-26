import kfp
from kfp import dsl
from kfp.compiler import Compiler
import kfp.components as components
import requests
from kubernetes import client as k8s_client

class FlexiPipeline():
    def __init__(self, config_path):
        """
        Initialize the FlexiPipeline class with the configuration path.
        
        Args:
            config_path (str): Path to the JSON configuration file.
        """
        self.config_data = self.read_json(config_path)
       
    def read_json(self, path):
        """
        Read and parse a JSON file from the given path.
        
        Args:
            path (str): Path to the JSON file.
        
        Returns:
            dict: Parsed JSON data.
        """
        import json
        with open(path, 'r') as file:
            cf = json.load(file)
        import pprint
        pprint.pprint(cf)
        return cf
    
    @staticmethod
    def pre_process():
        """
        Pre-processing function to be executed before the main processing.
        """
        import time
        print("Pre processing...")
        time.sleep(5)
        print("Pre processing done...")

    @staticmethod
    def custom_process(config_data: dict, image_id: str):
        """
        Custom processing function to process each image.
        
        Args:
            config_data (dict): Configuration data.
            image_id (str): ID of the image to be processed.
        """
        import os
        import sys
        import logging
            
        code_path = config_data['pipeline_config']['code_path']
        logging.info(os.listdir(code_path))
        sys.path.append(code_path)

        # Import the custom processing module
        from process import CustomProcess

        try:
            # Process implementation
            print("code_path: ", code_path)
            print(f"Running Custom Process for image id {image_id}...")
            obj = CustomProcess(5)
            param = config_data['process_input']['input_parameter']
            print(param)
        except Exception as e:
            print("Exception", e)

    @staticmethod
    def post_process():
        """
        Post-processing function to be executed after the main processing.
        """
        import time
        print("Post processing...")
        time.sleep(5)
        print("Post processing done...")     
    
    def get_pre_process_fn(self):
        """
        Get the pre-processing function.
        
        Returns:
            function: Pre-processing function.
        """
        return self.pre_process
    
    def get_custom_process_fn(self):
        """
        Get the custom processing function.
        
        Returns:
            function: Custom processing function.
        """
        return self.custom_process
    
    def get_post_process_fn(self):
        """
        Get the post-processing function.
        
        Returns:
            function: Post-processing function.
        """
        return self.post_process
    
    def pipeline(self, image_ids):
        """
        Define the pipeline for processing images.
        
        Args:
            image_ids (list): List of image IDs to be processed.
        
        Returns:
            function: The pipeline function.
        """
        
        config_data = self.config_data
        
        pre_process_fn = self.get_pre_process_fn()
        custom_process_fn = self.get_custom_process_fn()
        post_process_fn = self.get_post_process_fn()

        @dsl.pipeline("Process Name", "Process Description")
        def custom_process_pipeline(self):

            packages_installation = config_data['pipeline_config']['packages_to_install']
           
            # Define the code PVC (Persistent Volume Claim) --------------------------------------------------------------------------------
            code_mount = k8s_client.V1VolumeMount(
                    name=config_data['pipeline_config']['pvc']['name'], 
                    mount_path= config_data['pipeline_config']['pvc']['mount_path'])
            code_volume = k8s_client.V1Volume(
                    name=config_data['pipeline_config']['pvc']['name'], 
                    persistent_volume_claim=k8s_client.V1PersistentVolumeClaimVolumeSource(
                        claim_name=config_data['pipeline_config']['pvc']['name']))
            
            # Pre-process task
            create_pre_process_op = components.create_component_from_func(
                                                func=pre_process_fn,
                                                base_image="python:3.9"
                                                )
            create_pre_process_task = create_pre_process_op()
            create_pre_process_task.execution_options.caching_strategy.max_cache_staleness = "P0D" # Disable caching
            create_pre_process_task.set_retry(1, policy="Always", backoff_duration="2m")

            # Custom process tasks for each image ID
            create_custom_process_op = components.create_component_from_func(
                                                func=custom_process_fn,
                                                base_image="python:3.9",
                                                packages_to_install=packages_installation
                                                )
            tasks = []
            for image_id in image_ids:
                task = create_custom_process_op(
                    config_data=config_data, 
                    image_id=image_id
                    )  \
                    .set_memory_request(config_data['pipeline_config']['custom_process']['memory_request']) \
                    .set_cpu_request(config_data['pipeline_config']['custom_process']['cpu_request']) \
                    .set_memory_limit(config_data['pipeline_config']['custom_process']['memory_limit']) \
                    .set_cpu_limit(config_data['pipeline_config']['custom_process']['cpu_limit'])
                task.add_volume_mount(code_mount)
                task.add_volume(code_volume)
                task.execution_options.caching_strategy.max_cache_staleness = "P0D" # Disable caching
                
                task.set_display_name(f"Process for image id {image_id}")
                task.set_retry(1, policy="Always", backoff_duration="2m")
                task.after(create_pre_process_task)
                tasks.append(task)

            # Post-process task
            create_post_process_op = components.create_component_from_func(
                                                func=post_process_fn,
                                                base_image="python:3.9"
                                                )
            create_post_process_task = create_post_process_op()
            create_post_process_task.execution_options.caching_strategy.max_cache_staleness = "P0D" # Disable caching
            create_post_process_task.set_retry(1, policy="Always", backoff_duration="2m")

            # Ensure the post-process task runs after all custom process tasks
            for task in tasks:
                create_post_process_task.after(task)

        return custom_process_pipeline
    
    def create_run(self, image_ids):
        """
        Create and start a new run of the pipeline.
        
        Args:
            image_ids (list): List of image IDs to be processed.
        
        Returns:
            str: The run ID of the created pipeline run.
        """
        import datetime
        import requests

        kubeflow_endpoint = self.config_data['pipeline_config']['kubeflow_endpoint']
        username = self.config_data['pipeline_config']['username']
        password = self.config_data['pipeline_config']['password']

        # Authenticate with the Kubeflow endpoint
        session = requests.Session()
        response = session.get(kubeflow_endpoint)
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"login": username, "password": password}
        session.post(response.url, headers=headers, data=data)
        session_cookie = session.cookies.get_dict()["authservice_session"]

        # Create a client for the Kubeflow Pipelines
        client = kfp.Client(host=f"{kubeflow_endpoint}/pipeline", cookies=f"authservice_session={session_cookie}")
        print("Image_ids in create run:", image_ids)

        try: 
            # Generate a timestamp for the run name
            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            # Create and start the pipeline run
            run_id = client.create_run_from_pipeline_func(
                                self.pipeline(image_ids), {},
                                run_name=f"custom_process_run_{timestamp}",
                                experiment_name="custom-process-exp").run_id
            print("Custom process run created successfully:", run_id)
            return run_id
        except Exception as e:
            print("Exception:", e)