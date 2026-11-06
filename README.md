# End-to-End Data Management Pipeline for Animal Identification

## Project description
This repository contains a full ingestion and transformation pipeline for data with the purpose of using it in tasks based on animal identification and information gathering. This is aimed to be a tool for educators and researchers to easily obtain multi-modal relevant data. 
The project separates the stages the data goes through in zones, which can be found in the aptly named zones folder and then uses the resuts for a set of tasks, the implementation of which can be found in the task folder. These tasks can be interacted with through a streamlit based frontend, which is found in the frontend folder.

## How to run
To run the project in this repository first clone it. 

Before taking any steps it is recommended to create and activate a Python virtual environment:

````python
python3 -m venv .venv
source .venv/bin/activate
````

With this environment created, all dependencies required to run the scripts are listed in the **requirements.txt** file and can simply be installed through pip using 

`pip install -r requirements.txt`

There are two further steps to setup. First is the creation of a **.env file** which will include the setup for **minio** and **chromadb**. 
You can use the template for this **.env_template**, it must contain the following contents: 
```python
MINIO_ROOT_USER= #Admin name for the minio instance
MINIO_ROOT_PASSWORD= #Password for the minio instance
MINIO_ENDPOINT_URL=http://localhost:9000 #Can be changed
    
CHROMA_PATH = #Folder name to store persistent chroma data in
    
HF_TOKEN = #Optional: HuggingFace token to speed embeddings up
```

The second step is the preparation of a **docker container** to run the minio in. The docker compose file is already included in the repository so it only requires to have docker installed and running and then use the following command:

`docker compose up -d` 

Once all dependencies have been installed and the docker container raised, the entire pipeline can be executed by running the **pipeline.py script**. This executes all zones sequentially and generates the required output files, which are saved in their respective zone folders.

If only a specific script needs to be executed, it can be run individually using:
`python -m zones.zone_name.data_type`

Finally, to obtain the results for a specific task a streamlit app has to be started. To do so, simply run:
`streamlit run frontend/app.py`

This will automatically bring you to the locally run Streamlit page, were you can interact with each task by switching pages.