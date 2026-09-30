import json

with open(r'C:\Users\DELL\.gemini\antigravity\brain\2ae177ef-23f7-439b-9542-6a638413f8c3\.system_generated\logs\transcript_full.jsonl', 'r', encoding='utf-8') as f:
    lines = f.readlines()

user_inputs = [json.loads(line) for line in lines if '"USER_INPUT"' in line]
last_user_prompt = user_inputs[-1]['content']

with open('last_prompt.txt', 'w', encoding='utf-8') as out:
    out.write(last_user_prompt)

print(f"Wrote last user prompt ({len(last_user_prompt)} chars) to last_prompt.txt")
