import asyncio
import json
import logging
from openai import OpenAI
from openai.types.chat import (
    ChatCompletionMessage,
    ChatCompletionMessageParam,
    ChatCompletionToolUnionParam,
    ChatCompletionToolMessageParam,
)
from dotenv import load_dotenv
import os

from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

logger = logging.getLogger(__name__)
logging.basicConfig(filename="z3-chat.log", encoding="utf-8", level=logging.INFO)

MODEL = "gpt-4o-mini"  # small, cheaper OpenAI model

MAX_TOOL_CALLS = 5  # prevent infinite loops

SYSTEM_PROMPT = """
You are a formal reasoning assistant.

When given a problem:
1. Translate it into a valid SMT-LIB v2 script.
2. Call the `check_smt` tool with the SMT-LIB as a string.
3. Do not attempt to solve the problem yourself.
4. Use the solver result to answer the user.
"""

# Example SMT prompt.
user_prompt = """
Is there an integer x such that: x is greater than 5 and x is less than 3?
"""

initial_chat_context: list[ChatCompletionMessageParam] = [
    {"role": "system", "content": SYSTEM_PROMPT}
]


def load_api_key() -> OpenAI:
    load_dotenv()
    # Set your OpenAI API key from environment variable
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    if not client:
        raise ValueError(
            "API key not found. Please create a .env file and set the 'API_KEY'."
        )
    logger.info("API Key loaded successfully!")
    return client


async def call_llm(
    client: OpenAI,
    mcp: ClientSession,
    openai_tools: list[ChatCompletionToolUnionParam],
    chat_context: list[ChatCompletionMessageParam],
    num_tool_calls: int,
) -> int:
    response = client.chat.completions.create(
        model=MODEL, messages=chat_context, tools=openai_tools, tool_choice="auto"
    )

    message = response.choices[0].message
    logger.info("\n***LLM Response***")
    logger.info(message)
    if message is None:
        raise ValueError("LLM response is None")
    else:
        logger.info(message)

    # Check if the model called a tool
    if message.tool_calls:
        # Convert ChatCompletionMessage to ChatCompletionAssistantMessageParam
        assistant_message: ChatCompletionMessageParam = {
            "role": "assistant",
            "content": message.content,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": call.type,
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
                for call in message.tool_calls
                if call.type == "function" and hasattr(call, "function")
            ],
        }
        chat_context.append(assistant_message)
        for call in message.tool_calls:
            num_tool_calls += 1
            # MCP tools are always function type
            if call.type == "function" and hasattr(call, "function"):
                tool_name = call.function.name
                raw_args = json.loads(call.function.arguments)
                # Fix parameter names by removing trailing colons if present
                tool_args = {k.rstrip(":"): v for k, v in raw_args.items()}

                # Call the MCP tool
                result = await mcp.call_tool(tool_name, tool_args)
                logger.info(f"Tool: {tool_name}")
                result_content = result.content[0]
                logger.info(f"Result: {result_content}")
                if result_content.type == "text":
                    # logger.info("Tool output:", result_content.text)
                    response_context: ChatCompletionMessageParam
                    response_context = ChatCompletionToolMessageParam(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": result_content.text,
                        }
                    )
                    chat_context.append(response_context)
                    return num_tool_calls
                else:
                    raise ValueError("unexpected result type")
    else:
        logger.info("Non-tool response: %s", message.content)
        chat_context.append({"role": "assistant", "content": message.content})
        return num_tool_calls
    # This return is unreachable, but ensures all code paths return a string
    return 0


async def chat_loop() -> None:
    # Start the MCP server as a subprocess
    server_params = StdioServerParameters(
        command="python",
        args=["z3_mcp_server.py"],
    )

    client = load_api_key()
    chat_context = initial_chat_context

    async with stdio_client(server_params) as streams:
        async with ClientSession(*streams) as mcp:
            # Initialize the session
            await mcp.initialize()

            # Discover MCP tools
            tools = await mcp.list_tools()

            # Convert MCP tools to OpenAI function format
            openai_tools = []
            for tool in tools.tools:
                openai_tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.inputSchema,
                        },
                    }
                )

            num_tool_calls = 0

            while True:
                last_response = chat_context[-1]

                if last_response["role"] == "tool":
                    if num_tool_calls >= MAX_TOOL_CALLS:
                        print("Maximum tool calls reached.")
                        # Call the LLM one last time without tool calls. Response should be printed on next loop.
                        tcs = await call_llm(
                            client,
                            mcp,
                            openai_tools=[],
                            chat_context=chat_context,
                            num_tool_calls=0,
                        )
                        num_tool_calls = 0
                    else:
                        # This was an MCP response. Append tool response to chat context and call LLM again.
                        tcs = await call_llm(
                            client,
                            mcp,
                            openai_tools=openai_tools,
                            chat_context=chat_context,
                            num_tool_calls=num_tool_calls,
                        )
                        num_tool_calls += tcs

                elif last_response["role"] == "system":
                    # Initial call to the LLM. Prompt user for input.
                    user_input = input("User input: ")
                    chat_context.append({"role": "user", "content": user_input})

                elif last_response["role"] == "user":
                    # This was a user input. Call the LLM.
                    tcs = await call_llm(
                        client, mcp, openai_tools, chat_context, num_tool_calls
                    )
                    num_tool_calls += tcs

                elif last_response["role"] == "assistant":
                    # This was an LLM response. Check if it called a tool.
                    content = last_response.get("content")
                    if content is not None:
                        print("LLM response:", content)
                    user_input = input("User input: ")
                    chat_context.append({"role": "user", "content": user_input})

                else:
                    # We got an actual response from the LLM. Print it, get more input from the user and loop.
                    raise ValueError(f"Unexpected role: {last_response['role']}")


if __name__ == "__main__":
    asyncio.run(chat_loop())
