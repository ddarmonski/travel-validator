# utils.py

from azure.storage.blob import BlobServiceClient
from django.conf import settings
import uuid
import logging
from datetime import datetime, timedelta
import base64
from pdf2image import convert_from_bytes
import openai
import io, json, re

logger = logging.getLogger(__name__)



def get_blob_client():
    return BlobServiceClient.from_connection_string(settings.AZURE_STORAGE['CONNECTION_STRING'])

def upload_to_blob_storage(file, container_name="reports"):
    """
    Upload a file to Azure Blob Storage and return its URL
    """
    try:
        # Generate unique blob name
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_id = str(uuid.uuid4())[:8]
        blob_name = f"{timestamp}_{unique_id}_{file.name}"
        
        # Get blob client
        blob_service_client = get_blob_client()
        container_client = blob_service_client.get_container_client(container_name)
        blob_client = container_client.get_blob_client(blob_name)

        # Upload file
        file.seek(0)  # Ensure we're at the start of the file
        blob_client.upload_blob(file, overwrite=True)
        
        return blob_client.url

    except Exception as e:
        logger.error(f"Error uploading to blob storage: {str(e)}")
        raise Exception(f"Failed to upload file: {str(e)}")

def upload_multiple_files(files, container_name="reports"):
    """
    Upload multiple files to Azure Blob Storage
    Returns a list of dictionaries containing file information
    """
    uploaded_files = []
    
    for file in files:
        try:
            file_url = upload_to_blob_storage(file, container_name)
            uploaded_files.append({
                'name': file.name,
                'size': file.size,
                'url': file_url
            })
        except Exception as e:
            # If any file fails, attempt to clean up already uploaded files
            logger.error(f"Error during multiple file upload: {str(e)}")
            cleanup_uploaded_files(uploaded_files)
            raise Exception(f"Failed to upload {file.name}: {str(e)}")
    
    return uploaded_files

def cleanup_uploaded_files(uploaded_files):
    """
    Clean up uploaded files in case of an error
    """
    blob_service_client = get_blob_client()
    container_client = blob_service_client.get_container_client("reports")
    
    for file_info in uploaded_files:
        try:
            # Extract blob name from URL
            blob_name = file_info['url'].split('/')[-1]
            blob_client = container_client.get_blob_client(blob_name)
            blob_client.delete_blob()
        except Exception as e:
            logger.error(f"Error cleaning up blob: {str(e)}")

def convert_pdfs_to_base64_images(pdf_files):
    """
    Convert multiple PDF files to base64 encoded images
    
    Args:
        pdf_files: List of uploaded PDF files
        
    Returns:
        list: List of base64 encoded images from all PDFs
    """
    try:
        all_base64_images = []
        
        for pdf_file in pdf_files:
            # Read PDF content
            pdf_content = pdf_file.read()
            
            # Convert PDF pages to images
            images = convert_from_bytes(pdf_content)
            
            # Convert each image to base64
            for image in images:
                # Convert PIL image to bytes
                img_byte_arr = io.BytesIO()
                image.save(img_byte_arr, format='JPEG', quality=85)  # Reduced quality for better performance
                img_byte_arr = img_byte_arr.getvalue()
                
                # Convert to base64
                base64_image = base64.b64encode(img_byte_arr).decode('utf-8')
                all_base64_images.append(base64_image)
                
            # Reset file pointer for potential future use
            pdf_file.seek(0)
            
        return all_base64_images
        
    except Exception as e:
        logger.error(f"Error converting PDFs to images: {str(e)}")
        raise Exception(f"Failed to convert PDFs to images: {str(e)}")

def call_openai_api(base64_images, schema):
    """
    Call OpenAI API to extract information from images according to provided schema
    
    Args:
        base64_images: List of base64 encoded images
        schema: JSON schema defining the structure of information to extract
        
    Returns:
        str: JSON string containing extracted information
    """
    try:
        client = openai.AzureOpenAI(
            api_key=settings.AZURE_OPENAI['KEY'],
            azure_deployment=settings.AZURE_OPENAI['DEPLOYMENT'],
            api_version=settings.AZURE_OPENAI['API_VERSION'],
            azure_endpoint=settings.AZURE_OPENAI['ENDPOINT']
        )
        # Create system message with schema
        system_message = {
            "role": "system",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "You are an AI assistant that extracts information from travel reports "
                        "and maps it to a specific JSON schema. Return only the JSON data without "
                        "any additional explanations. If you can't find specific information, use null "
                        f"for that field. Here is the schema to follow: {schema}"
                    )
                }
            ]
        }

        # Process each image
        all_responses = []
        for base64_image in base64_images:
            response = client.chat.completions.create(
                model="gpt4o",
                messages=[
                    system_message,
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=2500,
                temperature=0.1
            )

            print(response.choices[0].message.content)
            
            all_responses.append(response.choices[0].message.content)

        # Return all responses
        return all_responses

    except Exception as e:
        logger.error(f"Error calling OpenAI API: {str(e)}")
        raise Exception(f"Failed to process images with OpenAI: {str(e)}")
    
def extract_json_from_text(text):
    """
    Robustly extract JSON from text that might contain markdown or other content.
    Searches for valid JSON arrays or objects in the text.
    
    Args:
        text (str): Text that might contain JSON content
        
    Returns:
        dict/list/None: Parsed JSON content or None if no valid JSON found
        
    Examples:
        >>> extract_json_from_text('```json\n{"a": 1}\n```')
        {'a': 1}
        >>> extract_json_from_text('Some text [{"a": 1}] more text')
        [{'a': 1}]
        >>> extract_json_from_text('Invalid content')
        None
    """
    if not text or not isinstance(text, str):
        return None

    try:
        # First try: direct JSON parsing
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

        # Second try: Remove markdown code blocks
        cleaned = re.sub(r'```(?:json)?\n?(.*?)\n?```', r'\1', text, flags=re.DOTALL)
        cleaned = cleaned.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Third try: Find JSON array or object patterns
        # Look for array pattern first
        array_match = re.search(r'\[.*?\]', text, re.DOTALL)
        if array_match:
            try:
                return json.loads(array_match.group())
            except json.JSONDecodeError:
                pass

        # Look for object pattern
        object_match = re.search(r'\{.*?\}', text, re.DOTALL)
        if object_match:
            try:
                return json.loads(object_match.group())
            except json.JSONDecodeError:
                pass

        # Final try: Look for the most promising {...} or [...] content
        # This handles nested structures better
        stack = []
        start = -1
        potential_jsons = []

        for i, char in enumerate(text):
            if char in '{[':
                if not stack:
                    start = i
                stack.append(char)
            elif char in '}]':
                if not stack:
                    continue
                if (char == '}' and stack[-1] == '{') or (char == ']' and stack[-1] == '['):
                    stack.pop()
                    if not stack:  # Complete JSON structure found
                        potential_jsons.append(text[start:i+1])

        # Try to parse each potential JSON string
        for json_str in potential_jsons:
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                continue

        logger.warning(f"Could not extract valid JSON from text: {text[:100]}...")
        return None

    except Exception as e:
        logger.error(f"Error extracting JSON: {str(e)}")
        return None