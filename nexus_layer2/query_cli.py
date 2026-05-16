"""
Nexus Layer 2 - Interactive Query CLI
Interactive terminal REPL for querying the CTG in plain English
"""

import sys
import time
import os
from datetime import datetime
from nl_query import nl_query
from verify_graph import verify_graph
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

# Try to import colorama for colored output
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    HAS_COLOR = True
except ImportError:
    HAS_COLOR = False
    # Fallback to no colors
    class Fore:
        GREEN = CYAN = YELLOW = RED = MAGENTA = BLUE = WHITE = ""
    class Style:
        BRIGHT = RESET_ALL = ""


def print_banner():
    """Print ASCII art welcome banner"""
    banner = f"""
{Fore.CYAN}{Style.BRIGHT}
==============================================================
                                                           
   N E X U S   C T G   Q U E R Y   I N T E R F A C E
                                                           
        Causal Temporal Graph - Natural Language
                                                           
==============================================================
{Style.RESET_ALL}
{Fore.WHITE}Welcome to the Nexus CTG Query Interface!
Ask questions in plain English about the PostgreSQL decision graph.
{Style.RESET_ALL}
"""
    print(banner)


def print_example_questions():
    """Print example questions users can ask"""
    examples = [
        "What are the most dangerous assumptions in the codebase?",
        "What decisions are already showing decay signals?",
        "What led to the MVCC tuple versioning decision?",
        "What does the WAL design depend on?",
        "Show me all foundational decisions",
        "What workarounds exist in the storage layer?",
        "What changed in the last 2 years?",
        "What would break if the process model assumption changed?"
    ]
    
    print(f"\n{Fore.YELLOW}{Style.BRIGHT}[?] EXAMPLE QUESTIONS:{Style.RESET_ALL}")
    for i, question in enumerate(examples, 1):
        print(f"{Fore.WHITE}  {i}. {question}{Style.RESET_ALL}")
    print()


def print_help():
    """Print help information"""
    print(f"\n{Fore.CYAN}{Style.BRIGHT}[*] SPECIAL COMMANDS:{Style.RESET_ALL}")
    print(f"{Fore.WHITE}  * help     - Show example questions")
    print(f"  * stats    - Show current graph statistics")
    print(f"  * clear    - Clear the screen")
    print(f"  * exit     - Exit the CLI")
    print(f"  * quit     - Exit the CLI")
    print(f"  * Ctrl+C   - Exit the CLI{Style.RESET_ALL}")
    print()
    print_example_questions()


def clear_screen():
    """Clear the terminal screen"""
    import os
    os.system('cls' if os.name == 'nt' else 'clear')


def check_neo4j_connection(uri: str = "bolt://localhost:7687") -> bool:
    """Check if Neo4j is running and accessible"""
    try:
        driver = GraphDatabase.driver(uri, auth=None)
        with driver.session() as session:
            session.run("RETURN 1")
        driver.close()
        return True
    except (ServiceUnavailable, AuthError) as e:
        return False
    except Exception as e:
        return False


def print_neo4j_error():
    """Print helpful error message when Neo4j is not running"""
    print(f"\n{Fore.RED}{Style.BRIGHT}[X] ERROR: Cannot connect to Neo4j{Style.RESET_ALL}")
    print(f"\n{Fore.YELLOW}[!] To start Neo4j, run:{Style.RESET_ALL}")
    print(f"{Fore.WHITE}   docker run -p 7474:7474 -p 7687:7687 neo4j:community{Style.RESET_ALL}")
    print(f"\n{Fore.YELLOW}[!] Then load the graph:{Style.RESET_ALL}")
    print(f"{Fore.WHITE}   python nexus_layer2/graph_builder.py{Style.RESET_ALL}")
    print()


def format_query_result(result: str, execution_time: float) -> str:
    """Format query result with colors and execution time"""
    output = []
    
    # Add execution time
    output.append(f"\n{Fore.GREEN}[>] Query executed in {execution_time:.2f}s{Style.RESET_ALL}\n")
    
    # Format the result with colors
    lines = result.split('\n')
    for line in lines:
        if line.startswith('•'):
            # Bullet points in cyan
            output.append(f"{Fore.CYAN}{line}{Style.RESET_ALL}")
        elif line.startswith('Found') or line.startswith('Graph Statistics'):
            # Headers in bright yellow
            output.append(f"{Fore.YELLOW}{Style.BRIGHT}{line}{Style.RESET_ALL}")
        elif 'DPR-' in line:
            # Lines with DPR IDs in white
            output.append(f"{Fore.WHITE}{line}{Style.RESET_ALL}")
        elif line.strip().startswith('-'):
            # Sub-items in light gray
            output.append(f"{Fore.WHITE}{line}{Style.RESET_ALL}")
        else:
            output.append(line)
    
    return '\n'.join(output)


def run_repl():
    """Run the interactive REPL loop"""
    # Print banner
    print_banner()
    
    # Check Neo4j connection
    print(f"{Fore.YELLOW}[*] Checking Neo4j connection...{Style.RESET_ALL}")
    if not check_neo4j_connection():
        print_neo4j_error()
        return
    
    print(f"{Fore.GREEN}[+] Connected to Neo4j{Style.RESET_ALL}\n")
    
    # Show graph stats
    print(f"{Fore.CYAN}{Style.BRIGHT}[i] CURRENT GRAPH STATUS:{Style.RESET_ALL}")
    print("=" * 60)
    try:
        verify_graph()
    except Exception as e:
        print(f"{Fore.RED}❌ Error loading graph stats: {e}{Style.RESET_ALL}")
        print_neo4j_error()
        return
    
    # Show example questions
    print_example_questions()
    
    # REPL loop
    print(f"{Fore.GREEN}{Style.BRIGHT}[+] Ready! Type your question or 'help' for examples.{Style.RESET_ALL}\n")
    
    while True:
        try:
            # Prompt
            question = input(f"{Fore.MAGENTA}{Style.BRIGHT}nexus> {Style.RESET_ALL}").strip()
            
            # Handle empty input
            if not question:
                continue
            
            # Handle special commands
            if question.lower() in ['exit', 'quit', 'q']:
                print(f"\n{Fore.CYAN}[*] Thank you for using Nexus CTG Query Interface!{Style.RESET_ALL}")
                print(f"{Fore.WHITE}Goodbye!{Style.RESET_ALL}\n")
                break
            
            elif question.lower() == 'help':
                print_help()
                continue
            
            elif question.lower() == 'stats':
                print(f"\n{Fore.CYAN}{Style.BRIGHT}[i] GRAPH STATISTICS:{Style.RESET_ALL}")
                print("=" * 60)
                try:
                    verify_graph()
                except Exception as e:
                    print(f"{Fore.RED}[X] Error: {e}{Style.RESET_ALL}")
                print()
                continue
            
            elif question.lower() == 'clear':
                clear_screen()
                print_banner()
                print(f"{Fore.GREEN}[+] Screen cleared. Type 'help' for examples.{Style.RESET_ALL}\n")
                continue
            
            # Execute natural language query
            print()
            start_time = time.time()
            
            try:
                result = nl_query(question)
                execution_time = time.time() - start_time
                
                # Format and print result
                formatted_result = format_query_result(result, execution_time)
                print("=" * 60)
                print(formatted_result)
                print("=" * 60)
                print()
                
            except ServiceUnavailable:
                print(f"\n{Fore.RED}[X] Lost connection to Neo4j{Style.RESET_ALL}")
                print_neo4j_error()
                break
            
            except Exception as e:
                print(f"\n{Fore.RED}[X] Error executing query: {e}{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}[!] Try rephrasing your question or type 'help' for examples.{Style.RESET_ALL}\n")
        
        except KeyboardInterrupt:
            print(f"\n\n{Fore.CYAN}[*] Interrupted. Goodbye!{Style.RESET_ALL}\n")
            break
        
        except EOFError:
            print(f"\n\n{Fore.CYAN}[*] Goodbye!{Style.RESET_ALL}\n")
            break


def main():
    """Main entry point"""
    try:
        run_repl()
    except Exception as e:
        print(f"\n{Fore.RED}[X] Fatal error: {e}{Style.RESET_ALL}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

# Made with Bob