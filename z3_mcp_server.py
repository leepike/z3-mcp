import sys
from mcp.server import FastMCP
from z3 import Solver, parse_smt2_string, sat, unknown

# Create an MCP server
server = FastMCP("z3-mcp-server")


@server.tool()
async def check_smt(smtlib: str) -> dict:
    """
    Check satisfiability of an SMT-LIB problem using Z3.

    Returns:
        {
            "result": "sat" | "unsat" | "unknown" | "error",
            "model": optional string,
            "reason": optional string,
            "error": optional string
        }
    """
    solver = Solver()
    try:
        solver.add(parse_smt2_string(smtlib))
    except Exception as e:
        return {"result": "error", "error": str(e)}

    res = solver.check()

    if res == sat:
        return {"result": "sat", "model": str(solver.model())}
    if res == unknown:
        return {"result": "unknown", "reason": solver.reason_unknown()}
    return {"result": "unsat"}


if __name__ == "__main__":
    # Only print to stderr — stdout is reserved for MCP JSON-RPC
    print("Z3 MCP server starting...", file=sys.stderr, flush=True)
    server.run()  # blocking
