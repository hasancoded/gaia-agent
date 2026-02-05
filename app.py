"""
GAIA Agent Application
A Gradio-based interface for the GAIA benchmark challenge using Hugging Face Inference API.

This application allows users to:
- Test the agent on random questions
- Generate submission files for the GAIA leaderboard
- Check configuration status
"""

import os
import sys
import json
import warnings
import gradio as gr
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Fix Windows console encoding for emoji support
if sys.platform == 'win32':
    import io
    # Use line_buffering=True to ensure output appears immediately
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True)

from tools import WebSearchTool, FileReaderTool, CalculatorTool
from gaia_client import GAIAClient
from agent import GAIAAgent

# Suppress Python 3.13 asyncio warnings
warnings.filterwarnings("ignore", category=RuntimeWarning, module="asyncio")
if sys.version_info >= (3, 13):
    import asyncio
    # Prevent event loop cleanup warnings
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())


# =============================================================================
# INITIALIZATION
# =============================================================================

def initialize_components():
    """Initialize all components needed for the GAIA agent."""
    print("[INIT] Initializing GAIA Agent Application...")
    
    # Get GAIA API URL from environment
    gaia_api_url = os.environ.get("GAIA_API_URL")
    if not gaia_api_url:
        print("[WARN] GAIA_API_URL not set in environment")
        gaia_api_url = "https://placeholder-url.com"
    
    print(f"[INIT] Using GAIA API: {gaia_api_url}")
    
    # Initialize tools
    search_tool = WebSearchTool()
    file_reader_tool = FileReaderTool(gaia_api_url)
    calculator_tool = CalculatorTool()
    
    # Initialize GAIA client
    gaia_client = GAIAClient(gaia_api_url)
    
    # Initialize agent with tools
    agent = GAIAAgent(tools={
        "search": search_tool,
        "file_reader": file_reader_tool,
        "calculator": calculator_tool
    })
    
    print("[OK] All components initialized successfully!\n")
    
    return gaia_api_url, gaia_client, agent


GAIA_API_URL, gaia_client, agent = initialize_components()


# =============================================================================
# CORE FUNCTIONS
# =============================================================================

def test_single_question():
    """Test the agent on one random question."""
    print("\n" + "="*70)
    print(" TESTING AGENT ON RANDOM QUESTION")
    print("="*70 + "\n")
    
    # Get a random question
    question_data = gaia_client.get_random_question()
    
    if not question_data:
        return (
            "[ERROR] Failed to get question from API. Please check:\n"
            "1. GAIA_API_URL is set correctly\n"
            "2. API is accessible\n"
            "3. Your internet connection"
        )
    
    # Extract task_id and question with multiple possible field names
    task_id = question_data.get("task_id") or question_data.get("id")
    question_text = (
        question_data.get("Question") or 
        question_data.get("question") or 
        question_data.get("text") or
        question_data.get("query")
    )
    
    # Debug: print the actual response structure if question is None
    if question_text is None:
        print(f"[WARN] Could not find question text in response")
        print(f"[DEBUG] Available fields: {list(question_data.keys())}")
        print(f"[DEBUG] Full response: {question_data}")
        return f"[ERROR] Could not extract question from API response.\n\nAvailable fields: {list(question_data.keys())}\n\nFull response:\n{question_data}"
    
    print(f"[TASK] Task ID: {task_id}")
    print(f"[TASK] Question: {question_text}\n")
    
    # Get answer with reasoning
    try:
        answer, reasoning = agent.answer_question(question_text, task_id)
        
        print(f"\n[OK] Agent's Answer: {answer}")
        print(f"[REASONING] {reasoning[:200]}...")
        print("\n" + "="*70 + "\n")
        
        result = f"""TASK ID: {task_id}

QUESTION:
{question_text}

AGENT ANSWER:
{answer}

REASONING TRACE:
{reasoning}

---
Test completed successfully.
"""
        return result
        
    except Exception as e:
        error_msg = f"[ERROR] Error during testing: {str(e)}"
        print(error_msg)
        return error_msg


def generate_submission_file(progress=gr.Progress()):
    """Generate the JSONL submission file for GAIA leaderboard."""
    print("\n" + "="*70)
    print(" GENERATING SUBMISSION FILE FOR GAIA LEADERBOARD")
    print("="*70 + "\n")
    
    # Get all questions
    questions = gaia_client.get_all_questions()
    
    if not questions:
        error_msg = f"""[ERROR] Failed to get questions from API.

Please check:
1. GAIA_API_URL is set correctly in Settings → Repository secrets
2. The API is accessible
3. Your internet connection

Current GAIA_API_URL: {GAIA_API_URL}"""
        print(error_msg)
        return None, error_msg
    
    print(f"[INFO] Retrieved {len(questions)} questions")
    print(f"[INFO] Estimated time: {len(questions) * 20} seconds (~{len(questions) * 20 // 60} minutes)\n")
    
    # Process each question
    results = []
    successful = 0
    failed = 0
    
    for i, q_data in enumerate(progress.tqdm(questions, desc="Processing questions")):
        # Extract task_id and question with multiple possible field names
        task_id = q_data.get("task_id") or q_data.get("id")
        question_text = (
            q_data.get("Question") or 
            q_data.get("question") or 
            q_data.get("text") or
            q_data.get("query")
        )
        
        if not question_text:
            print(f"[WARN] Question {i+1} has no text. Skipping...")
            continue
        
        print(f"\n{'─'*70}")
        print(f"[{i+1}/{len(questions)}] Task ID: {task_id}")
        print(f"Question: {question_text[:100]}...")
        
        try:
            # Get answer and reasoning
            answer, reasoning = agent.answer_question(question_text, task_id)
            
            # Create result entry
            result_entry = {
                "task_id": task_id,
                "model_answer": answer,
                "reasoning_trace": reasoning
            }
            results.append(result_entry)
            successful += 1
            
            print(f"[OK] Answer: {answer}")
            
        except Exception as e:
            print(f"[ERROR] Error processing question: {e}")
            # Still add an entry to maintain order
            results.append({
                "task_id": task_id,
                "model_answer": "Error",
                "reasoning_trace": f"Error: {str(e)}"
            })
            failed += 1
    
    # Write to JSONL file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    import tempfile
    output_file = os.path.join(tempfile.gettempdir(), f"gaia_submission_{timestamp}.jsonl")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        for result in results:
            f.write(json.dumps(result, ensure_ascii=False) + '\n')
    
    print(f"\n{'='*70}")
    print(f"[OK] SUBMISSION FILE GENERATED SUCCESSFULLY!")
    print(f"{'='*70}")
    print(f"[STATS] Statistics:")
    print(f"   Total questions: {len(results)}")
    print(f"   Successful: {successful}")
    print(f"   Failed: {failed}")
    print(f"   File: {output_file}")
    print(f"{'='*70}\n")
    
    # Create summary
    summary = f"""Submission file generated successfully!

STATISTICS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total questions processed: {len(results)}
Successfully answered: {successful}
Errors encountered: {failed}
Success rate: {(successful/len(results)*100):.1f}%

SAMPLE ENTRIES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Entry 1:
{json.dumps(results[0], indent=2, ensure_ascii=False)}

Entry 2:
{json.dumps(results[1], indent=2, ensure_ascii=False) if len(results) > 1 else 'N/A'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

NEXT STEPS:
1. Download the .jsonl file using the button above
2. Go to: https://huggingface.co/spaces/gaia-benchmark/leaderboard
3. Click "Submit a new model for evaluation"
4. Upload your file and fill in the form
5. Submit and wait for results!

Download the file above to submit to GAIA leaderboard.
"""
    
    return output_file, summary


def check_config():
    """Check if environment is properly configured."""
    status = "[OK] Configuration Check:\n\n"
    
    # Check HF API Token
    if os.environ.get("HF_API_TOKEN"):
        status += "[OK] HF_API_TOKEN: Configured\n"
    else:
        status += "[ERROR] HF_API_TOKEN: NOT FOUND\n"
    
    # Check Tavily API Key
    if os.environ.get("TAVILY_API_KEY"):
        status += "[OK] TAVILY_API_KEY: Configured\n"
    else:
        status += "[ERROR] TAVILY_API_KEY: NOT FOUND\n"
    
    # Check GAIA API URL
    if os.environ.get("GAIA_API_URL"):
        status += f"[OK] GAIA_API_URL: {os.environ.get('GAIA_API_URL')}\n"
    else:
        status += "[ERROR] GAIA_API_URL: NOT FOUND\n"
    
    return status


# =============================================================================
# GRADIO INTERFACE
# =============================================================================

def create_gradio_interface():
    """Create and configure the Gradio interface."""
    demo = gr.Blocks(title="GAIA Agent - HF Inference API")
    
    with demo:
        gr.Markdown("""
        # GAIA Agent - Hugging Face Inference API
        
        AI agent for the GAIA benchmark challenge using Hugging Face Inference API.
        
        ## Goal
        Generate a submission file for the [GAIA Leaderboard](https://huggingface.co/spaces/gaia-benchmark/leaderboard)
        
        ## Submission Requirements:
        - **Agent name**: e.g., "MyHFAgent-v1"
        - **Model family**: "Hugging Face Inference API (Kimi-K2)"
        - **System prompt**: See Submission Info tab
        - **URL**: Your HuggingFace Space URL
        - **Organisation**: Your name or organization
        - **Contact email**: Your email address
        """)
        
        with gr.Tab("Test Agent"):
            gr.Markdown("""
            ### Test Your Agent
            
            Test the agent on a random question to verify functionality.
            """)
            
            test_btn = gr.Button(
                "Test on Random Question",
                variant="primary",
                size="lg"
            )
            test_output = gr.Textbox(
                label="Test Results",
                lines=20
            )
            
            test_btn.click(
                fn=test_single_question,
                outputs=test_output
            )
        
        with gr.Tab("Generate Submission"):
            gr.Markdown("""
            ### Generate GAIA Submission File
            
            This will:
            1. Process all questions from the GAIA API
            2. Generate answers using HF Inference API
            3. Create a `.jsonl` file ready for submission
            4. Provide reasoning traces for each answer
            
            **Estimated time**: 10-15 minutes for all questions
            
            **Important**: Test your agent first before generating full submission.
            """)
            
            generate_btn = gr.Button(
                "Generate Submission File",
                variant="primary",
                size="lg"
            )
            
            output_file = gr.File(
                label="Download Submission File",
                file_types=[".jsonl"]
            )
            summary_output = gr.Textbox(
                label="Generation Summary",
                lines=30
            )
            
            generate_btn.click(
                fn=generate_submission_file,
                outputs=[output_file, summary_output]
            )
        
        with gr.Tab("Submission Info"):
            gr.Markdown("""
            ## GAIA Submission Requirements
            
            ### System Prompt Used by This Agent:
            ```
            You are a general AI assistant. I will ask you a question. 
            Report your thoughts, and finish your answer with the 
            following template: FINAL ANSWER: [YOUR FINAL ANSWER]. 
            YOUR FINAL ANSWER should be a number OR as few words as 
            possible OR a comma separated list of numbers and/or strings. 
            If you are asked for a number, don't use comma to write your 
            number neither use units such as $ or percent sign unless 
            specified otherwise. If you are asked for a string, don't 
            use articles, neither abbreviations (e.g. for cities), and 
            write the digits in plain text unless specified otherwise. 
            If you are asked for a comma separated list, apply the above 
            rules depending of whether the element to be put in the list 
            is a number or a string.
            ```
            
            ### Model Information:
            - **Model**: Hugging Face Inference API (moonshotai/Kimi-K2-Instruct-0905)
            - **Tools**: Web Search (Tavily), File Reader, Calculator
            - **Framework**: Custom agent implementation
            
            ### How to Submit:
            
            1. **Generate** your submission file using the "Generate Submission" tab
            2. **Download** the `.jsonl` file
            3. **Go to** [GAIA Leaderboard](https://huggingface.co/spaces/gaia-benchmark/leaderboard)
            4. **Click** "Submit a new model for evaluation"
            5. **Fill in** the form:
               - Agent name: `[YourName]-HFAgent-v1`
               - Model family: `Hugging Face Inference API (Kimi-K2)`
               - System prompt: Copy from above
               - URL: Your Space URL
               - Organisation: Your name
               - Email: Your email
            6. **Upload** your `.jsonl` file
            7. **Submit** and wait for results!
            
            ### Scoring:
            Your submission will be evaluated using exact match scoring:
            - **Numbers**: `$`, `%`, `,` are removed, then compared as floats
            - **Strings**: All whitespace and punctuation removed, lowercased
            - **Lists**: Split by `,` or `;`, each element compared individually
            
            ### Good Luck!
            """)
        
        with gr.Tab("Configuration"):
            gr.Markdown("""
            ### Configuration Status
            
            Check if your environment is properly configured.
            """)
            
            config_btn = gr.Button("Check Configuration")
            config_output = gr.Textbox(label="Configuration Status", lines=8)
            config_btn.click(fn=check_config, outputs=config_output)
    
    return demo


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    try:
        demo = create_gradio_interface()
        print("\n[INIT] Launching Gradio interface...")
        demo.launch(share=True)
    except KeyboardInterrupt:
        print("\n\n[EXIT] Shutting down gracefully...")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] Error launching application: {e}")
        sys.exit(1)