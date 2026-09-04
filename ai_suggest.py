import json
import os
from groq import Groq


def suggest_config_with_ai(user_input: str, available_components: list) -> dict:
    """
    Appelle Groq (Qwen 3.8-27b) pour suggérer une config PC.
    Retourne : {"status": "success", "config": [...]} ou {"status": "error", "message": "..."}
    """

    groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    # Construire le prompt
    component_list = json.dumps(available_components, indent=2, ensure_ascii=False)

    prompt = f"""Tu es un expert en configuration PC. L'utilisateur demande :
"{user_input}"

Voici les composants disponibles :
{component_list}

Retourne UNIQUEMENT un JSON valide (pas de texte avant/après) avec la structure :
{{
  "cpu": {{"id": ..., "nom": "..."}},
  "motherboard": {{"id": ..., "nom": "..."}},
  "ram": {{"id": ..., "nom": "..."}},
  "gpu": {{"id": ..., "nom": "..."}},
  "psu": {{"id": ..., "nom": "..."}},
  "case": {{"id": ..., "nom": "..."}},
  "storage": {{"id": ..., "nom": "..."}}
}}

Sélectionne les composants les plus adaptés à la demande. Les IDs doivent exister."""

    try:
        message = groq_client.messages.create(
            model="qwen-3.8-27b",  # Modèle Qwen 3.8
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = message.content[0].text.strip()

        # Parser la réponse JSON
        suggested_config = json.loads(response_text)

        return {"status": "success", "config": suggested_config}

    except json.JSONDecodeError as e:
        return {"status": "error", "message": f"IA a retourné du JSON invalide : {e}"}
    except Exception as e:
        return {"status": "error", "message": f"Erreur Groq : {str(e)}"}
