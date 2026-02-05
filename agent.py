import os
import re
import string
from huggingface_hub import InferenceClient


class GAIAAgent:
    """
    An AI agent that can answer GAIA benchmark questions
    using Hugging Face Inference API and various tools
    """
    
    def __init__(self, tools=None):
        """
        Initialize the agent with Hugging Face Inference API
        
        Args:
            tools: Dictionary of tools the agent can use
        """
        # Get HF API token from environment
        self.api_token = os.environ.get("HF_API_TOKEN")
        if not self.api_token:
            raise ValueError("ERROR: HF_API_TOKEN not found in environment variables")
        
        # Initialize HF Inference Client
        self.client = InferenceClient(token=self.api_token)
        
        # Model selection
        # Available models (tested and working):
        #   - moonshotai/Kimi-K2-Instruct-0905 (1.14s, excellent reasoning)
        #   - meta-llama/Llama-3.1-70B-Instruct (1.01s, fastest)
        #   - Qwen/Qwen2.5-72B-Instruct (1.17s, great for complex tasks)
        #   - meta-llama/Llama-3.1-8B-Instruct (1.20s, good balance)
        self.model_name = "moonshotai/Kimi-K2-Instruct-0905"
        
        self.tools = tools or {}
        
        print(f"[INFO] GAIA Agent initialized with HF Inference API ({self.model_name})")
    
    def answer_question(self, question_text, task_id=None):
        """
        Answer a GAIA question with reasoning trace
        
        Args:
            question_text: The question to answer
            task_id: Optional task ID (if question has associated files)
            
        Returns:
            tuple: (answer, reasoning_trace)
        """
        print(f"\n{'='*60}")
        print(f"[PROCESSING] Question: {question_text[:100]}...")
        print(f"{'='*60}")
        
        reasoning_steps = []
        reasoning_steps.append(f"Question: {question_text}")
        
        # Step 1: Analyze if we need tools
        needs_search = self._needs_web_search(question_text)
        needs_file = task_id and self._needs_file(question_text)
        
        if needs_search:
            reasoning_steps.append("✓ Determined web search is needed")
            print("  [SEARCH] Web search required")
        if needs_file:
            reasoning_steps.append("✓ Determined file reading is needed")
            print("  [FILE] File reading required")
        
        # Step 2: Gather context
        context = ""
        
        if needs_search and "search" in self.tools:
            print("  [SEARCH] Performing web search...")
            search_query = self._generate_search_query(question_text)
            reasoning_steps.append(f"Search query: {search_query}")
            
            search_results = self.tools["search"].search(search_query, max_results=8)
            context += f"\n\nWeb Search Results:\n{search_results}\n"
            reasoning_steps.append("✓ Search completed")
        
        if needs_file and "file_reader" in self.tools:
            print("  [FILE] Reading associated file...")
            file_content = self.tools["file_reader"].read_file(task_id)
            
            # Try to process the file content
            if isinstance(file_content, bytes) and len(file_content) > 0:
                # Check if it's an error message
                try:
                    error_check = file_content.decode('utf-8', errors='ignore')
                    if 'Failed to download' in error_check or 'Error' in error_check:
                        print(f"      [WARN] File download issue: {error_check}")
                        context += f"\n\nNote: File could not be downloaded. {error_check}\n"
                    else:
                        # Try to process as Excel file
                        if task_id:
                            try:
                                import pandas as pd
                                import io
                                
                                # Try to read as Excel
                                df = pd.read_excel(io.BytesIO(file_content))
                                excel_summary = f"Excel file contents (first 50 rows):\n{df.head(50).to_string()}\n\nColumn names: {list(df.columns)}\nTotal rows: {len(df)}"
                                context += f"\n\nFile Content:\n{excel_summary}\n"
                                reasoning_steps.append("✓ Excel file processed successfully")
                                print(f"      ✓ Excel file processed: {len(df)} rows, {len(df.columns)} columns")
                            except Exception as excel_error:
                                # Fall back to text interpretation
                                file_text = file_content.decode('utf-8', errors='ignore')[:2000]
                                context += f"\n\nFile Content (text interpretation):\n{file_text}\n"
                                reasoning_steps.append(f"✓ File processed as text (Excel parsing failed: {excel_error})")
                except Exception as e:
                    context += f"\n\nFile: [Binary file, {len(file_content)} bytes - could not parse]\n"
                    reasoning_steps.append(f"✓ File downloaded but could not be parsed: {e}")
            else:
                context += "\n\nNote: File could not be retrieved.\n"
                reasoning_steps.append("✗ File could not be retrieved")
            
            reasoning_steps.append("✓ File processing completed")
        
        # Step 3: Generate answer using GAIA format
        print("  🧠 Generating answer with Gemini...")
        answer, answer_reasoning = self._generate_answer_gaia_format(
            question_text, 
            context
        )
        reasoning_steps.append(answer_reasoning)
        
        # Step 4: Format answer for scorer
        final_answer = self._format_for_scorer(answer, question_text)
        reasoning_steps.append(f"Final formatted answer: {final_answer}")
        
        print(f"  [ANSWER] {final_answer}")
        print(f"{'='*60}\n")
        
        # Combine reasoning trace
        reasoning_trace = " | ".join(reasoning_steps)
        
        return final_answer, reasoning_trace
    
    def _needs_web_search(self, question):
        """Determine if question needs web search"""
        # Keywords that strongly suggest current/factual info needed
        search_keywords = [
            "current", "latest", "recent", "today", "now", "2024", "2025", "2026",
            "who is", "what is", "when did", "where is", "how many",
            "population", "price", "cost", "president", "CEO", "capital",
            "located", "founded", "born", "died", "released", "published"
        ]
        
        question_lower = question.lower()
        
        # Check for search keywords
        return any(keyword in question_lower for keyword in search_keywords)
    
    def _needs_file(self, question):
        """Determine if question needs file reading"""
        file_keywords = [
            "file", "image", "document", "picture", "photo", "shown",
            "attached", "provided", "given", "painting", "chart",
            "graph", "table", "spreadsheet", "pdf"
        ]
        
        question_lower = question.lower()
        return any(keyword in question_lower for keyword in file_keywords)
    
    def _generate_search_query(self, question):
        """Generate an effective search query from the question"""
        prompt = f"""Generate a concise, effective web search query to answer this question.
Return ONLY the search query, nothing else.

Question: {question}

Search query:"""

        try:
            response = self.model.generate_content(prompt)
            query = response.text.strip()
            print(f"      Generated query: {query}")
            return query
        except Exception as e:
            print(f"      ⚠️ Error generating search query: {e}")
            # Fallback: use first 10 words of question
            return " ".join(question.split()[:10])
    
    def _generate_answer_gaia_format(self, question, context=""):
        """
        Generate answer using official GAIA system prompt format
        """
        # Official GAIA system prompt
        system_instruction = """You are a general AI assistant. I will ask you a question. Report your thoughts, and finish your answer with the following template: FINAL ANSWER: [YOUR FINAL ANSWER]. YOUR FINAL ANSWER should be a number OR as few words as possible OR a comma separated list of numbers and/or strings. If you are asked for a number, don't use comma to write your number neither use units such as $ or percent sign unless specified otherwise. If you are asked for a string, don't use articles, neither abbreviations (e.g. for cities), and write the digits in plain text unless specified otherwise. If you are asked for a comma separated list, apply the above rules depending of whether the element to be put in the list is a number or a string."""
        
        # Construct the prompt
        if context:
            user_prompt = f"""Here is some information that may help answer the question:

{context}

Question: {question}

Remember: End your response with "FINAL ANSWER: [YOUR ANSWER]" following the formatting rules."""
        else:
            user_prompt = f"""Question: {question}

Remember: End your response with "FINAL ANSWER: [YOUR ANSWER]" following the formatting rules."""
        
        try:
            # Use HF Inference API
            response = self.client.chat_completion(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=2000
            )
            
            # Extract response
            full_response = response.choices[0].message.content
            
            # Extract final answer
            if "FINAL ANSWER:" in full_response:
                parts = full_response.split("FINAL ANSWER:")
                answer = parts[-1].strip()
                reasoning = parts[0].strip()
            else:
                # Fallback if format not followed
                answer = full_response.strip()
                reasoning = "Direct answer provided"
            
            return answer, reasoning
            
        except Exception as e:
            print(f"      [ERROR] Failed to generate answer: {e}")
            return "Error generating answer", str(e)
    
    def _format_for_scorer(self, answer, question):
        """
        Format answer to match GAIA scorer expectations
        """
        answer = answer.strip()
        
        # Remove common wrapper phrases
        prefixes_to_remove = [
            "the answer is ",
            "it is ",
            "that would be ",
            "i believe ",
            "i think ",
            "this is ",
        ]
        
        answer_lower = answer.lower()
        for prefix in prefixes_to_remove:
            if answer_lower.startswith(prefix):
                answer = answer[len(prefix):]
                answer = answer.strip()
                break
        
        # Remove surrounding quotes
        if (answer.startswith('"') and answer.endswith('"')) or \
           (answer.startswith("'") and answer.endswith("'")):
            answer = answer[1:-1]
        
        # Remove trailing periods
        answer = answer.rstrip('.')
        
        # Remove extra whitespace
        answer = ' '.join(answer.split())
        
        return answer.strip()