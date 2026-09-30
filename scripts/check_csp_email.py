import re

with open(r'C:\Users\DELL\.gemini\antigravity\brain\2ae177ef-23f7-439b-9542-6a638413f8c3\.system_generated\steps\7423\content.md', 'r', encoding='utf-8') as f:
    text = f.read()

emails = set(re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', text))
mailtos = set(re.findall(r'mailto:[^\s"\'<>]+', text))
print("Emails found on CSP page:", emails)
print("Mailtos found on CSP page:", mailtos)
