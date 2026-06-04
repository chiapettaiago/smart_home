"""Interpretação de comandos residenciais em linguagem natural com Gemini."""

import json

import requests

from app.config import GEMINI_API_KEY, GEMINI_MODEL


class GeminiIntegration:
    def __init__(self, api_key: str = GEMINI_API_KEY, model: str = GEMINI_MODEL):
        self.api_key = api_key
        self.model = model
        self.timeout = 20

    def interpret_command(self, message: str, devices: list, history: list = None, automation_context: dict = None) -> dict:
        if not self.api_key:
            return {
                "success": False,
                "message": "Configure GEMINI_API_KEY no arquivo .env para usar o assistente.",
            }

        response_schema = {
            "type": "object",
            "properties": {
                "reply": {
                    "type": "string",
                    "description": "Resposta curta em português para o usuário.",
                },
                "commands": {
                    "type": "array",
                    "description": "Comandos residenciais solicitados explicitamente pelo usuário.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "device_id": {"type": "integer"},
                            "action": {"type": "string"},
                            "params": {
                                "type": "object",
                                "additionalProperties": True,
                            },
                        },
                        "required": ["device_id", "action", "params"],
                        "additionalProperties": False,
                    },
                },
                "automations": {
                    "type": "array",
                    "description": "Automações a criar somente quando o usuário pedir explicitamente para criar/salvar automações.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "trigger": {"type": "string"},
                            "condition": {
                                "type": "object",
                                "additionalProperties": True,
                            },
                            "conditions": {
                                "type": "object",
                                "additionalProperties": True,
                            },
                            "actions": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "device_id": {"type": "integer"},
                                        "action": {"type": "string"},
                                        "params": {
                                            "type": "object",
                                            "additionalProperties": True,
                                        },
                                    },
                                    "required": ["device_id", "action", "params"],
                                    "additionalProperties": False,
                                },
                            },
                            "active": {"type": "boolean"},
                        },
                        "required": ["name", "trigger", "condition", "actions", "active"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["reply", "commands", "automations"],
            "additionalProperties": False,
        }
        catalog = json.dumps(devices, ensure_ascii=False)
        automation_catalog = json.dumps(automation_context or {}, ensure_ascii=False)
        system_prompt = (
            "Você controla uma casa inteligente. Responda sempre em português brasileiro. "
            "Use somente os dispositivos, IDs, ações e parâmetros presentes no catálogo abaixo. "
            "Não invente IDs ou ações. Gere comandos apenas quando o usuário pedir uma ação de forma clara. "
            "Você também pode ajudar a criar automações. Só preencha automations quando o usuário pedir explicitamente "
            "para criar, salvar, ativar ou aceitar uma automação. Para sugestões ou análises, explique no reply e deixe automations vazio. "
            "Ao criar automações, use somente triggers e condições documentados no catálogo de automação. "
            "Se usar uma sugestão aprendida, copie o payload automation da sugestão e ajuste apenas se o usuário pedir. "
            "Para perguntas, conversas ou pedidos ambíguos, responda normalmente e deixe commands vazio. "
            "Quando houver mais de um dispositivo correspondente e não estiver claro qual usar, peça esclarecimento. "
            "Não afirme que um comando foi executado; diga que ele será executado. "
            f"Catálogo JSON: {catalog}\n"
            f"Catálogo de automações e padrões aprendidos JSON: {automation_catalog}"
        )
        contents = [
            {
                "role": item["role"],
                "parts": [{"text": item["text"]}],
            }
            for item in (history or [])[-6:]
            if item.get("role") in {"user", "model"} and item.get("text")
        ]
        contents.append({"role": "user", "parts": [{"text": message}]})

        try:
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": self.api_key,
                },
                json={
                    "systemInstruction": {"parts": [{"text": system_prompt}]},
                    "contents": contents,
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "responseJsonSchema": response_schema,
                    },
                },
                timeout=self.timeout,
            )
            if response.status_code not in {200, 201}:
                return {
                    "success": False,
                    "message": f"Gemini retornou status {response.status_code}. Verifique a chave e o modelo configurados.",
                }
            payload = response.json()
            parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            text = "".join(part.get("text", "") for part in parts)
            result = json.loads(text)
            return {
                "success": True,
                "reply": result.get("reply") or "Comando interpretado.",
                "commands": result.get("commands") or [],
                "automations": result.get("automations") or [],
            }
        except requests.RequestException as exc:
            return {"success": False, "message": f"Não foi possível consultar o Gemini: {exc}"}
        except (IndexError, TypeError, ValueError, json.JSONDecodeError):
            return {"success": False, "message": "O Gemini retornou uma resposta inválida. Tente reformular o pedido."}
