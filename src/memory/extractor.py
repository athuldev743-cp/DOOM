import os
from src.agent.llm import chat
from src.memory.profile import ProfileManager

profile = ProfileManager()

EXTRACT_PROMPT = """You are a memory extractor. Analyze this conversation and extract any important facts about the user.

Extract facts like:
- Personal info (name, location, age, relationships)
- Career info (job, company, goals, interviews, salary expectations)
- Preferences (likes, dislikes, habits, schedule)
- Important events (meetings, interviews, deadlines, plans)
- Contacts mentioned (names, relationships, numbers)
- Skills and learning goals

Conversation:
{conversation}

Respond ONLY with a JSON array of facts. Each fact has:
- key: short snake_case identifier
- value: the fact
- category: one of [personal, career, preference, event, contact, skill]

Example:
[
  {{"key": "interview_zoho", "value": "Interview at Zoho next Tuesday", "category": "event"}},
  {{"key": "prefers_night_work", "value": "Prefers working at night", "category": "preference"}}
]

If no important facts found, return empty array: []
Only extract clear, specific facts. Do NOT extract generic conversation."""

async def extract_and_save(user_message: str, assistant_message: str):
    try:
        conversation = f"User: {user_message}\nAssistant: {assistant_message}"
        prompt = EXTRACT_PROMPT.format(conversation=conversation)
        
        response = await chat([
            {"role": "user", "content": prompt}
        ])
        
        # Parse JSON response
        import json
        import re
        
        # Extract JSON array from response
        match = re.search(r'\[.*\]', response, re.DOTALL)
        if not match:
            return
            
        facts = json.loads(match.group())
        
        if not facts:
            return
            
        for fact in facts:
            key = fact.get('key', '').strip()
            value = fact.get('value', '').strip()
            category = fact.get('category', 'general').strip()
            
            if key and value:
                profile.set(key, value, category)
                print(f"[Memory] Learned: {key} = {value}")
                
    except Exception as e:
        print(f"[Memory] Extraction error: {e}")