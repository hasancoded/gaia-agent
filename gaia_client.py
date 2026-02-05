import requests


class GAIAClient:
    """Client for interacting with GAIA benchmark API"""
    
    def __init__(self, api_url):
        """
        Initialize the GAIA client
        
        Args:
            api_url: Base URL of the GAIA API
        """
        self.api_url = api_url.rstrip('/')  # Remove trailing slash if present
        print(f"[INIT] GAIA Client initialized with URL: {self.api_url}")
    
    def get_all_questions(self):
        """
        Get all evaluation questions
        
        Returns:
            List of question dictionaries
        """
        try:
            url = f"{self.api_url}/questions"
            print(f"[API] Fetching questions from: {url}")
            
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            questions = response.json()
            print(f"[INFO] Retrieved {len(questions)} questions")
            return questions
            
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Error getting questions: {e}")
            return []
        except Exception as e:
            print(f"[ERROR] Unexpected error: {e}")
            return []
    
    def get_random_question(self):
        """
        Get one random question for testing
        
        Returns:
            Single question dictionary
        """
        try:
            url = f"{self.api_url}/random-question"
            print(f"[API] Fetching random question from: {url}")
            
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            question = response.json()
            print(f"[INFO] Retrieved random question")
            
            # Debug: Show available fields in response
            if isinstance(question, dict):
                print(f"   Available fields: {list(question.keys())}")
            
            return question
            
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Error getting random question: {e}")
            return None
        except Exception as e:
            print(f"[ERROR] Unexpected error: {e}")
            return None
    
    def get_file(self, task_id):
        """
        Download a file associated with a question
        
        Args:
            task_id: Task ID that has an associated file
            
        Returns:
            File content as bytes
        """
        try:
            url = f"{self.api_url}/files/{task_id}"
            print(f"[FILE] Downloading file for task {task_id}")
            
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            print(f"[INFO] File downloaded ({len(response.content)} bytes)")
            return response.content
            
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Error getting file: {e}")
            return None
        except Exception as e:
            print(f"[ERROR] Unexpected error: {e}")
            return None
    
    def submit_answers(self, username, code_link, answers):
        """
        Submit your answers for scoring
        
        Args:
            username: Your Hugging Face username
            code_link: URL to your Space code
            answers: List of {"task_id": "...", "submitted_answer": "..."}
            
        Returns:
            Result dictionary with score
        """
        try:
            url = f"{self.api_url}/submit"
            print(f"📤 Submitting {len(answers)} answers to: {url}")
            
            payload = {
                "username": username,
                "agent_code": code_link,
                "answers": answers
            }
            
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            print(f"[INFO] Submission successful")
            return result
            
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Error submitting answers: {e}")
            return {"error": str(e)}
        except Exception as e:
            print(f"[ERROR] Unexpected error: {e}")
            return {"error": str(e)}