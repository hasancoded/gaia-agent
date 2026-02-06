"""
GAIA Agent Application
A Gradio-based interface for the GAIA benchmark challenge using Hugging Face Inference API (Llama-3.1-70B) with automatic Groq fallback (Llama-3.3-70B).

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
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True)

# Suppress Python 3.13 asyncio warnings
warnings.filterwarnings("ignore", category=RuntimeWarning, module="asyncio")
if sys.version_info >= (3, 13):
    import asyncio
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())


# =============================================================================
# LAZY INITIALIZATION (for HF Spaces SSR compatibility)
# =============================================================================

def get_components():
    """Lazy initialization of components."""
    from tools import WebSearchTool, FileReaderTool, CalculatorTool
    from gaia_client import GAIAClient
    from agent import GAIAAgent
    
    gaia_api_url = os.environ.get("GAIA_API_URL", "https://placeholder-url.com")
    
    search_tool = WebSearchTool()
    file_reader_tool = FileReaderTool(gaia_api_url)
    calculator_tool = CalculatorTool()
    gaia_client = GAIAClient(gaia_api_url)
    
    agent = GAIAAgent(tools={
        "search": search_tool,
        "file_reader": file_reader_tool,
        "calculator": calculator_tool
    })
    
    return gaia_api_url, gaia_client, agent


# =============================================================================
# CORE FUNCTIONS
# =============================================================================

def test_single_question():
    """Test the agent on one random question."""
    try:
        gaia_api_url, gaia_client, agent = get_components()
        
        print("\n" + "="*70)
        print(" TESTING AGENT ON RANDOM QUESTION")
        print("="*70 + "\n")
        
        question_data = gaia_client.get_random_question()
        
        if not question_data:
            return (
                "[ERROR] Failed to get question from API. Please check:\n"
                "1. GAIA_API_URL is set correctly\n"
                "2. API is accessible\n"
                "3. Your internet connection"
            )
        
        task_id = question_data.get("task_id") or question_data.get("id")
        question_text = (
            question_data.get("Question") or 
            question_data.get("question") or 
            question_data.get("text") or
            question_data.get("query")
        )
        
        if question_text is None:
            print(f"[WARN] Could not find question text in response")
            print(f"[DEBUG] Available fields: {list(question_data.keys())}")
            return f"[ERROR] Could not extract question from API response.\n\nAvailable fields: {list(question_data.keys())}"
        
        file_name = question_data.get("file_name")
        
        print(f"[TASK] Task ID: {task_id}")
        print(f"[TASK] Question: {question_text}")
        if file_name:
            print(f"[TASK] File: {file_name}\n")
        else:
            print()
        
        answer, reasoning = agent.answer_question(question_text, task_id, file_name)
        
        print(f"\n[OK] Agent's Answer: {answer}")
        print(f"[REASONING] {reasoning[:200]}...")
        print("\n" + "="*70 + "\n")
        
        return f"""TASK ID: {task_id}

QUESTION:
{question_text}

AGENT ANSWER:
{answer}

REASONING TRACE:
{reasoning}

---
Test completed successfully.
"""
    except Exception as e:
        error_msg = f"[ERROR] Error during testing: {str(e)}"
        print(error_msg)
        return error_msg


def generate_submission_file():
    """Generate the JSONL submission file for GAIA leaderboard."""
    try:
        gaia_api_url, gaia_client, agent = get_components()
        
        print("\n" + "="*70)
        print(" GENERATING SUBMISSION FILE FOR GAIA LEADERBOARD")
        print("="*70 + "\n")
        
        questions = gaia_client.get_all_questions()
        
        if not questions:
            return f"[ERROR] Failed to get questions. GAIA_API_URL: {gaia_api_url}"
        
        print(f"[INFO] Retrieved {len(questions)} questions")
        print(f"[INFO] Estimated time: {len(questions) * 20} seconds (~{len(questions) * 20 // 60} minutes)\n")
        
        results = []
        successful = 0
        failed = 0
        
        for i, q_data in enumerate(questions):
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
            
            file_name = q_data.get("file_name")
            
            print(f"\n{'─'*70}")
            print(f"[{i+1}/{len(questions)}] Task ID: {task_id}")
            print(f"Question: {question_text[:100]}...")
            if file_name:
                print(f"File: {file_name}")
            
            try:
                answer, reasoning = agent.answer_question(question_text, task_id, file_name)
                results.append({
                    "task_id": task_id,
                    "model_answer": answer,
                    "reasoning_trace": reasoning
                })
                successful += 1
                print(f"[OK] Answer: {answer}")
            except RuntimeError as e:
                # API credit depletion - stop processing
                error_msg = str(e)
                print(f"\\n[CRITICAL] {error_msg}")
                print(f"[INFO] Stopping early after {i+1} questions due to API credit exhaustion.")
                results.append({
                    "task_id": task_id,
                    "model_answer": "API credits exhausted",
                    "reasoning_trace": error_msg
                })
                failed += 1
                break  # Stop processing more questions
            except Exception as e:
                print(f"[ERROR] Error processing question: {e}")
                results.append({
                    "task_id": task_id,
                    "model_answer": "Error",
                    "reasoning_trace": f"Error: {str(e)}"
                })
                failed += 1
        
        print(f"\n{'='*70}")
        print(f"[OK] SUBMISSION FILE GENERATED SUCCESSFULLY!")
        print(f"{'='*70}")
        print(f"[STATS] Statistics:")
        print(f"   Total questions: {len(results)}")
        print(f"   Successful: {successful}")
        print(f"   Failed: {failed}")
        print(f"{'='*70}\n")
        
        # Create JSONL content
        jsonl_content = "\n".join(json.dumps(r, ensure_ascii=False) for r in results)
        
        output = f"""=== SUBMISSION FILE GENERATED ===

Statistics:
- Total: {len(results)}
- Successful: {successful}
- Failed: {failed}
- Success rate: {(successful/len(results)*100):.1f}%

SAMPLE ENTRIES:
{json.dumps(results[0], indent=2, ensure_ascii=False) if results else 'N/A'}

=== COPY BELOW AND SAVE AS submission.jsonl ===

{jsonl_content}

=== END OF FILE ===

NEXT STEPS:
1. Copy the JSONL content above (between the === markers)
2. Save it as 'submission.jsonl'
3. Go to: https://huggingface.co/spaces/gaia-benchmark/leaderboard
4. Upload your file!
"""
        return output
        
    except Exception as e:
        return f"[ERROR] {str(e)}"


def check_config():
    """Check if environment is properly configured."""
    status = "[OK] Configuration Check:\n\n"
    
    if os.environ.get("HF_API_TOKEN"):
        status += "[OK] HF_API_TOKEN: Configured\n"
    else:
        status += "[ERROR] HF_API_TOKEN: NOT FOUND\n"
    
    if os.environ.get("TAVILY_API_KEY"):
        status += "[OK] TAVILY_API_KEY: Configured\n"
    else:
        status += "[ERROR] TAVILY_API_KEY: NOT FOUND\n"
    
    if os.environ.get("GAIA_API_URL"):
        status += f"[OK] GAIA_API_URL: {os.environ.get('GAIA_API_URL')}\n"
    else:
        status += "[ERROR] GAIA_API_URL: NOT FOUND\n"
        
    if os.environ.get("GROQ_API_KEY"):
        status += "[OK] GROQ_API_KEY: Configured (Fallback Enabled)\n"
    else:
        status += "[WARN] GROQ_API_KEY: NOT FOUND (Fallback Disabled)\n"
    
    return status


# =============================================================================
# GRADIO INTERFACE
# =============================================================================

with gr.Blocks(title="GAIA Agent - HF Inference API") as demo:
    gr.Markdown("""
    # GAIA Agent - Hugging Face Inference API
    
    AI agent for the GAIA benchmark challenge using Hugging Face Inference API (Llama-3.1-70B) with automatic Groq fallback (Llama-3.3-70B).
    
    ## Goal
    Generate a submission file for the [GAIA Leaderboard](https://huggingface.co/spaces/gaia-benchmark/leaderboard)
    
    ## Submission Requirements:
    - **Agent name**: e.g., "MyHFAgent-v1"
    - **Model family**: "Llama-3.1-70B / Llama-3.3-70B (Hybrid)"
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
        3. Create a `.jsonl` content ready for submission
        4. Provide reasoning traces for each answer
        
        **Estimated time**: 10-15 minutes for all questions
        
        **Note**: Copy the JSONL output and save as .jsonl file
        """)
        
        generate_btn = gr.Button(
            "Generate Submission File",
            variant="primary",
            size="lg"
        )
        summary_output = gr.Textbox(
            label="Submission Content (copy and save as .jsonl)",
            lines=30
        )
        
        generate_btn.click(
            fn=generate_submission_file,
            outputs=summary_output
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
        - **Primary Model**: Hugging Face Inference API (meta-llama/Llama-3.1-70B-Instruct)
        - **Fallback Model**: Groq API (llama-3.3-70b-versatile)
        - **Tools**: Web Search (Tavily), File Reader, Calculator
        - **Framework**: Custom agent implementation
        
        ### How to Submit:
        
        1. **Generate** your submission file using the "Generate Submission" tab
        2. **Copy** the JSONL content from the output
        3. **Save** as `submission.jsonl`
        4. **Go to** [GAIA Leaderboard](https://huggingface.co/spaces/gaia-benchmark/leaderboard)
        5. **Click** "Submit a new model for evaluation"
        6. **Fill in** the form:
           - Agent name: `[YourName]-HFAgent-v1`
           - Model family: `Llama-3.1-70B / Llama-3.3-70B (Hybrid)`
           - System prompt: Copy from above
           - URL: Your Space URL
           - Organisation: Your name
           - Email: Your email
        7. **Upload** your `.jsonl` file
        8. **Submit** and wait for results!
        
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

# Launch at module level (required for HF Spaces SSR compatibility)
demo.launch()
