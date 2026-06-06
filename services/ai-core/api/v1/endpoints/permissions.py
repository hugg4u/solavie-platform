from fastapi import APIRouter

router = APIRouter()

@router.get("/manifest")
async def get_permissions_manifest():
    """
    Expose dynamic permission manifest of AI Core for Dashboard configuration.
    """
    return {
        "service": "ai-core",
        "resources": [
            {
                "name": "chats",
                "description": "AI completions and agent loops",
                "actions": ["create"]
            },
            {
                "name": "configs",
                "description": "AI system configurations",
                "actions": ["read", "write"]
            },
            {
                "name": "prompts",
                "description": "Prompt templates management",
                "actions": ["read", "write"]
            },
            {
                "name": "analytics",
                "description": "AI usage and metrics reports",
                "actions": ["read"]
            }
        ]
    }
