
import os
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()

ROLE_PROVIDER_MAP = {
    "execution_planning": {
        "provider": "mistral", 
        "model": "mistral-small-latest",
        "fallbacks": [
            {"provider": "mistral2", "model": "mistral-small-latest"},
            # {"provider": "gemini", "model": "gemini-2.5-flash"},
            {"provider": "zai", "model": "GLM-4.7-Flash"}
        ]
    },

    "triage": {
        "provider": "mistral3", 
        "model": "mistral-small-latest",
        "fallbacks":[
            {"provider": "gemini", "model": "gemini-2.5-flash"},
            {"provider": "gemini2", "model": "gemini-2.5-flash"},
            {"provider": "zai", "model": "GLM-4.7-Flash"}
        ]
    },

    "execution_result": {
        "provider": "groq2", 
        "model": "openai/gpt-oss-120b",
        "fallbacks":[
            {"provider": "groq_fallback", "model": "openai/gpt-oss-120b"},
            # {"provider": "gemini", "model": "gemini-2.5-flash"},
            {"provider": "mistral2", "model": "mistral-small-latest"},
            {"provider": "zai", "model": "GLM-4.7-Flash"}
        ]
    },

    "summarization": {
        "provider": "gemini", 
        "model": "gemini-2.5-flash",
        "fallbacks":[
            {"provider": "groq_fallback", "model": "openai/gpt-oss-120b"},
            # {"provider": "gemini", "model": "gemini-2.5-flash"},
            # {"provider": "mistral", "model": "mistral-small-latest"},
            {"provider": "zai", "model": "GLM-4.7-Flash"}
        ]
    },
}


def _build_gemini_client(model: str, temperature: float = 0.2):
    # pyrefly: ignore [missing-import]
    from langchain_google_genai import ChatGoogleGenerativeAI
    print("inside the gemini llm config")

    api_key = os.environ.get("GOOGLE_API_KEY")
    # print(f"Api Key: {api_key}")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY not set in environment (.env)")
    return ChatGoogleGenerativeAI(model=model, google_api_key=api_key, temperature=temperature)


def _build_gemini_client2(model: str, temperature: float = 0.2):
    # pyrefly: ignore [missing-import]
    from langchain_google_genai import ChatGoogleGenerativeAI
    print("inside the gemini 2 llm config")

    api_key = os.environ.get("GOOGLE_API_KEY2")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY2 not set in environment (.env)")
    return ChatGoogleGenerativeAI(model=model, google_api_key=api_key, temperature=temperature)


def _build_ollama_client(model: str, temperature: float = 0.2):
    # pyrefly: ignore [missing-import]
    from langchain_ollama import ChatOllama
    print("inside the ollama llm config")

    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    return ChatOllama(model=model, base_url=base_url, temperature=temperature)


def _build_openrouter_client(model: str, temperature: float = 0.2):
    # pyrefly: ignore [missing-import]
    from langchain_openai import ChatOpenAI
    print("inside the openrouter llm config")

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set in environment (.env)")
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        temperature=temperature,
    )


def _build_mistral_client(model: str, temperature: float = 0.1):
    from langchain_mistralai import ChatMistralAI
    print("inside the mistral llm config")

    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY not set in environment (.env)")
    return ChatMistralAI(model=model, mistral_api_key=api_key, temperature=temperature)

def _build_mistral_client2(model: str, temperature: float = 0.2):
    from langchain_mistralai import ChatMistralAI
    print("inside the mistral 2 llm config")
    api_key = os.environ.get("MISTRAL_API_KEY2")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY2 not set in environment (.env)")
    return ChatMistralAI(model=model, mistral_api_key=api_key, temperature=temperature)

def _build_mistral_client3(model: str, temperature: float = 0.2):
    from langchain_mistralai import ChatMistralAI

    api_key = os.environ.get("MISTRAL_API_KEY3")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY3 not set in environment (.env)")
    return ChatMistralAI(model=model, mistral_api_key=api_key, temperature=temperature)




def _build_groq_client(model: str, temperature: float = 0.2):
    api_key = os.environ.get("GROQ_API_KEY_SUMMARIZATION") or os.environ.get("GROQ_API_KEY")
    print("inside the groq1 llm config")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY / GROQ_API_KEY_SUMMARIZATION not set in environment (.env)")
    try:
        # pyrefly: ignore [missing-import]
        from langchain_groq import ChatGroq
        return ChatGroq(model_name=model, groq_api_key=api_key, temperature=temperature)
    except ImportError:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
            temperature=temperature,
        )


def _build_groq_client2(model: str, temperature: float = 0.2):
    api_key = os.environ.get("GROQ_API_KEY_EXECUTION_RESULT") or os.environ.get("GROQ_API_KEY2")
    print("inside the groq2 llm config")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY_EXECUTION_RESULT / GROQ_API_KEY2 not set in environment (.env)")
    try:
        # pyrefly: ignore [missing-import]
        from langchain_groq import ChatGroq
        return ChatGroq(model_name=model, groq_api_key=api_key, temperature=temperature)
    except ImportError:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
            temperature=temperature,
        )


def _build_groq_fallback_client(model: str, temperature: float = 0.2):
    api_key = os.environ.get("GROQ_API_KEY_FALLBACK")
    print("inside the groq llm config")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY_FALLBACK not set in environment (.env)")
    try:
        # pyrefly: ignore [missing-import]
        from langchain_groq import ChatGroq
        return ChatGroq(model_name=model, groq_api_key=api_key, temperature=temperature)
    except ImportError:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
            temperature=temperature,
        )


def _build_zai_client(model: str = "GLM-4.7-Flash", temperature: float = 0.2):
    """Builds a ChatOpenAI client configured for Z.ai / Zhipu GLM models."""
    # pyrefly: ignore [missing-import]
    from langchain_openai import ChatOpenAI
    print("Inside the z.ai llm config")
    api_key = (
        os.environ.get("ZAI_API_KEY")
        or os.environ.get("ZHIPUAI_API_KEY")
        or os.environ.get("GLM_API_KEY")
    )
    if not api_key:
        raise RuntimeError("ZAI_API_KEY / ZHIPUAI_API_KEY / GLM_API_KEY not set in environment (.env)")
    
    base_url = (
        os.environ.get("ZAI_BASE_URL")
        or os.environ.get("ZHIPUAI_BASE_URL")
        or "https://api.z.ai/api/paas/v4/"
    )
    target_model = model or os.environ.get("ZAI_MODEL", "GLM-4.7-Flash")
    return ChatOpenAI(
        model=target_model,
        openai_api_key=api_key,
        openai_api_base=base_url,
        temperature=temperature,
    )


_BUILDERS = {
    "gemini": _build_gemini_client,
    "groq": _build_groq_client,
    "groq2": _build_groq_client2,
    "groq_fallback": _build_groq_fallback_client,
    "ollama": _build_ollama_client,
    "openrouter": _build_openrouter_client,
    "mistral": _build_mistral_client,
    "mistral2": _build_mistral_client2,
    "mistral3": _build_mistral_client3,
    "gemini2": _build_gemini_client2,
    "zai": _build_zai_client,
    "glm": _build_zai_client,
    "z_ai": _build_zai_client,
}


@lru_cache(maxsize=32)
def get_llm(role: str, temperature: float = 0.2):
    """
    Returns a LangChain chat model client for the given agent role.
    `role` must be a key in ROLE_PROVIDER_MAP above.
    Cached so repeated calls for the same role reuse the same client instance.
    """
    if role not in ROLE_PROVIDER_MAP:
        raise ValueError(f"Unknown role '{role}'. Add it to ROLE_PROVIDER_MAP first.")
    config = ROLE_PROVIDER_MAP[role]
    builder = _BUILDERS[config["provider"]]
    primary_llm = builder(config["model"], temperature=temperature)
    
    if "fallbacks" in config:
        fallback_llms = []
        for fb_config in config["fallbacks"]:
            try:
                fb_builder = _BUILDERS[fb_config["provider"]]
                fallback_llms.append(fb_builder(fb_config["model"], temperature=temperature))
            except Exception:
                # If a fallback provider is missing keys in development, skip it gracefully
                pass
        if fallback_llms:
            return primary_llm.with_fallbacks(fallback_llms)
        
    return primary_llm
