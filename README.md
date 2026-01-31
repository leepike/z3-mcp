# Z3 MCP Server

Simple/toy MCP (Model Context Protocol) server that integrates the Z3 theorem prover with OpenAI for formal reasoning and satisfiability checking.

1. Translates natural language problems into SMT-LIB v2 format
2. Sends them to Z3 for satisfiability checking
3. Returns results (sat/unsat/unknown) back to the language model

## Components

- **z3_mcp_server.py** - MCP server that exposes Z3's `check_smt` tool.
- **z3_client.py** - Example client that connects the MCP server to OpenAI's API for interactive problem solving.

## Installation

It is recommended to use a Pythonvirtual environment.
Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`
```

```bash
pip install z3-solver mcp openai python-dotenv
```

## Setup

1. Create a `.env` file with your OpenAI API key:
   ```
   OPENAI_API_KEY=your_key_here
   ```

2. Run the client (this will spin up the server as well):
   ```bash
   python z3_client.py
   ```

## Example Usage

The client can solve problems like:
- "Is there an integer x such that: x > 5 and x < 3?"
- Constraint satisfaction problems
- Logical reasoning puzzles
