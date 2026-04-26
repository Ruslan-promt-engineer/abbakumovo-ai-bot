import os
import requests
import json  # 🔹 Импорт перенесен в начало файла
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

API_KEY = os.getenv("YANDEXGPT_API_KEY")
FOLDER_ID = os.getenv("FOLDER_ID")

# 🔹 Актуальный эндпоинт для YandexGPT
API_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

def test_llm_connection():
    """Тестирует подключение к YandexGPT"""
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Api-Key {API_KEY}",
        "x-folder-id": FOLDER_ID
    }
    
    # 🔹 Правильный формат для YandexGPT
    data = {
        "modelUri": f"gpt://{FOLDER_ID}/yandexgpt/latest",
        "completionOptions": {
            "stream": False,
            "temperature": 0.3,
            "maxTokens": 100
        },
        "messages": [
            {"role": "system", "text": "Ты полезный ассистент."},
            {"role": "user", "text": "Напиши только слово 'Успех'."}
        ]
    }
    
    try:
        logger.info("Отправляем запрос к YandexGPT...")
        response = requests.post(API_URL, headers=headers, json=data)
        logger.info(f"Статус ответа: {response.status_code}")
        
        if response.status_code != 200:
            logger.error(f"Тело ответа: {response.text}")
        
        response.raise_for_status()
        
        result = response.json()
        # 🔹 Безопасное извлечение текста
        text = result.get("result", {}).get("alternatives", [{}])[0].get("message", {}).get("text", "")
        
        logger.success(f"✅ YandexGPT подключен! Ответ: {text}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка подключения: {e}")
        return False


def analyze_ticket(user_message: str, has_photo: bool = False) -> dict:
    """
    Анализирует сообщение от арендатора и извлекает данные для заявки
    Возвращает: dict с полями office_number, category, priority, description
    """
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Api-Key {API_KEY}",
        "x-folder-id": FOLDER_ID
    }
    
    # 🔹 Промпт для извлечения данных из заявки
    system_prompt = """Ты — интеллектуальный диспетчер офисно-складского комплекса "Аббакумово".
Твоя задача: анализировать сообщения арендаторов и извлекать структурированные данные для создания заявки.

Верни ТОЛЬКО валидный JSON объект в таком формате:
{
    "office_number": "номер офиса/склада/помещения или null",
    "company_name": "название компании или null",
    "phone": "номер телефона в формате +7... или null",
    "category": "электрика | сантехника | техническое | другое",
    "priority": "срочно | высокий | средний | низкий",
    "description": "краткое описание проблемы 1-2 предложения",
    "needs_clarification": "вопрос арендатору если данных критически не хватает, или null"
}

ПРАВИЛА:
1. Если сообщение описывает проблему (протечка, поломка, отсутствие света, запах, течь и т.д.) — СОЗДАВАЙ ЗАЯВКУ даже без номера офиса. Ставь office_number: null.
2. Если название компании не указано — поставь null.
3. Приоритет: "срочно", "протечка", "запах газа", "искрит", "затопление", "течь" → срочно/высокий. Остальное → средний.
4. Заполняй needs_clarification ТОЛЬКО если сообщение совершенно непонятно (например, просто "привет", "как дела", вопрос по аренде/оплате). В этом случае: category: "другое", needs_clarification: "Уточните, пожалуйста, суть обращения по эксплуатации помещения".
5. НИКОГДА не проси уточнить телефон или офис, если есть описание проблемы. Просто ставь null в эти поля.
6. Верни ТОЛЬКО чистый JSON, без пояснений и тройных кавычек."""

    user_text = f"Сообщение от арендатора: {user_message}"
    if has_photo:
        user_text += "\n\n[К сообщению прикреплено фото]"

    data = {
        "modelUri": f"gpt://{FOLDER_ID}/yandexgpt/latest",
        "completionOptions": {
            "stream": False,
            "temperature": 0.2,  # 🔹 Низкая температура для стабильного JSON
            "maxTokens": 500
        },
        "messages": [
            {"role": "system", "text": system_prompt},
            {"role": "user", "text": user_text}
        ]
    }
    
    try:
        logger.info(f"Анализируем заявку: {user_message[:50]}...")
        response = requests.post(API_URL, headers=headers, json=data)
        response.raise_for_status()
        
        result = response.json()
        llm_response = result["result"]["alternatives"][0]["message"]["text"]
        
        logger.info(f"Сырой ответ LLM: {llm_response[:200]}...")
        
        # 🔹 🔹 🔹 ОЧИСТКА ОТ MARKDOWN (ГЛАВНОЕ ИСПРАВЛЕНИЕ) 🔹 🔹 🔹
        llm_response = llm_response.strip()
        
        # Удаляем блоки кода вида ```json ... ``` или просто ``` ... ```
        if llm_response.startswith("```"):
            # Ищем первую открывающую скобку и последнюю закрывающую
            start_idx = llm_response.find("{")
            end_idx = llm_response.rfind("}") + 1
            if start_idx != -1 and end_idx != -1:
                llm_response = llm_response[start_idx:end_idx]
                logger.info("Очищено от markdown-разметки")
        
        # 🔹 Парсим JSON из ответа
        parsed_data = json.loads(llm_response)
        
        logger.success("✅ Заявка проанализирована!")
        return parsed_data
        
    except json.JSONDecodeError as e:
        logger.error(f"❌ Ошибка парсинга JSON: {e}")
        logger.error(f"Полученный текст: {llm_response}")
        # Возвращаем дефолтные значения, чтобы бот не упал
        return {
            "office_number": None,
            "company_name": None,
            "category": "другое",
            "priority": "средний",
            "description": user_message,
            "needs_clarification": "Не удалось автоматически разобрать заявку. Пожалуйста, уточните: номер офиса, суть проблемы"
        }
    except Exception as e:
        logger.error(f"❌ Ошибка анализа заявки: {e}")
        return None
# =============================================================================
# 🔹 УНИВЕРСАЛЬНАЯ ФУНКЦИЯ ДЛЯ ЗАПРОСОВ К YANDEXGPT
# =============================================================================

def ask_yandex_gpt(prompt: str, system_prompt: str = None, temperature: float = 0.3, max_tokens: int = 1000) -> str:
    """
    Универсальная функция для запросов к YandexGPT.
    
    Args:
        prompt: Текст запроса пользователя
        system_prompt: Системная инструкция для модели (опционально)
        temperature: Креативность (0.0 - точно, 1.0 - креативно)
        max_tokens: Максимальная длина ответа
    
    Returns:
        str: Ответ модели
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Api-Key {API_KEY}",
        "x-folder-id": FOLDER_ID
    }
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "text": system_prompt})
    messages.append({"role": "user", "text": prompt})
    
    data = {
        "modelUri": f"gpt://{FOLDER_ID}/yandexgpt/latest",
        "completionOptions": {
            "stream": False,
            "temperature": temperature,
            "maxTokens": max_tokens
        },
        "messages": messages
    }
    
    try:
        response = requests.post(API_URL, headers=headers, json=data)
        response.raise_for_status()
        
        result = response.json()
        text = result.get("result", {}).get("alternatives", [{}])[0].get("message", {}).get("text", "")
        
        # 🔹 Очистка от markdown-блоков, если есть
        text = text.strip()
        if text.startswith("```"):
            start_idx = text.find("{") if "{" in text else 0
            end_idx = text.rfind("}") + 1 if "}" in text else len(text)
            if start_idx != -1 and end_idx != -1:
                text = text[start_idx:end_idx]
        
        return text
        
    except Exception as e:
        logger.error(f"❌ Ошибка YandexGPT: {e}")
        raise  # Пробрасываем ошибку вверх, чтобы обработать в main.py

# 🔹 Тестовый запуск
if __name__ == "__main__":
    print("\n=== 🧪 ТЕСТ LLM МОДУЛЯ ===\n")
    
    print("1. Проверка подключения...")
    if test_llm_connection():
        print("✅ Подключение успешно!\n")
    else:
        print("❌ Подключение не удалось. Проверьте ключи.\n")
    
    print("2. Проверка анализа заявки...")
    test_message = "Срочно! Прорвало трубу в офисе 405. Компания Вектор."
    print(f"Вход: {test_message}")
    
    result = analyze_ticket(test_message)
    
    print("\n📊 Результат анализа:")
    if result:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("❌ Не удалось получить результат")