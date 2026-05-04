"""Script to fix the broken isSolutionGenerating / extractFinalAnswerFromAiText functions in training.html"""
import re

filepath = r'c:\Users\Maxim\PycharmProjects\ezolimp\frontend\training.html'

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# The broken code block to find and replace
old_block = """function isSolutionGenerating(sol, rawAiText = '') {
  const aiStatus = String(sol?.ai_solution_status || '').toLowerCase();
  const aiSource = String(sol?.ai_generation_source || '').toLowerCase();
  return aiStatus === 'generating'
    || String(sol?.free_ai_status || '').toLowerCase() === 'generating'
    || aiSource === 'queued'
    || aiSource === 'queued_existing'
    || isAiTemplateText(rawAiText);
    if (candidate) return candidate;
  }

  const lines = raw.split(/\\r?\\n/).map(line => line.trim()).filter(Boolean).slice(-20).reverse();
  for (const line of lines) {
    const match = line.match(/^\\s*(?:[-*\\u2022]\\s*)?(?:\\*\\*)?([^:\\n\\r]{1,80})(?:\\*\\*)?\\s*[:\\-]\\s*(.+)$/);
    if (!match || !match[2]) continue;
    const label = String(match[1] || '').toLowerCase().trim();
    const candidate = String(match[2] || '').trim();
    if (!candidate) continue;
    const compact = candidate.replace(/[\\s,;:]+/g, '');
    if (!compact) continue;
    if (!label.includes('answer') && !label.includes('\u043e\u0442\u0432\u0435\u0442') && (candidate.length > 160 || candidate.split(/\\s+/).length > 10)) {
      continue;
    }
    return candidate;
  }
  return '';
}"""

new_block = """function isSolutionGenerating(sol, rawAiText = '') {
  const aiStatus = String(sol?.ai_solution_status || '').toLowerCase();
  const aiSource = String(sol?.ai_generation_source || '').toLowerCase();
  return aiStatus === 'generating'
    || String(sol?.free_ai_status || '').toLowerCase() === 'generating'
    || aiSource === 'queued'
    || aiSource === 'queued_existing'
    || isAiTemplateText(rawAiText);
}

function extractFinalAnswerFromAiText(text) {
  const raw = String(text || '').trim();
  if (!raw) return '';
  // Match Russian "\u0418\u0442\u043e\u0433\u043e\u0432\u044b\u0439 \u043e\u0442\u0432\u0435\u0442:" / "\u041e\u0442\u0432\u0435\u0442:" and English "Final answer:"
  const patterns = [
    /(?:^|\\n)\\s*(?:[-*\\u2022]\\s*)?(?:\\*\\*)?(?:\u0438\u0442\u043e\u0433\u043e\u0432\u044b\u0439\\s+)?\u043e\u0442\u0432\u0435\u0442(?:\\*\\*)?\\s*[:\\-]\\s*([^\\n\\r]+)/im,
    /(?:^|\\n)\\s*(?:[-*\\u2022]\\s*)?(?:\\*\\*)?final\\s+answer(?:\\*\\*)?\\s*[:\\-]\\s*([^\\n\\r]+)/im,
  ];
  for (const pattern of patterns) {
    const match = raw.match(pattern);
    if (match) {
      const candidate = String(match[1] || '').replace(/\\*\\*/g, '').trim();
      if (candidate) return candidate;
    }
  }

  const lines = raw.split(/\\r?\\n/).map(line => line.trim()).filter(Boolean).slice(-20).reverse();
  for (const line of lines) {
    const match = line.match(/^\\s*(?:[-*\\u2022]\\s*)?(?:\\*\\*)?([^:\\n\\r]{1,80})(?:\\*\\*)?\\s*[:\\-]\\s*(.+)$/);
    if (!match || !match[2]) continue;
    const label = String(match[1] || '').toLowerCase().trim();
    const candidate = String(match[2] || '').replace(/\\*\\*/g, '').trim();
    if (!candidate) continue;
    const compact = candidate.replace(/[\\s,;:]+/g, '');
    if (!compact) continue;
    if (!label.includes('answer') && !label.includes('\u043e\u0442\u0432\u0435\u0442') && (candidate.length > 160 || candidate.split(/\\s+/).length > 10)) {
      continue;
    }
    return candidate;
  }
  return '';
}"""

# Normalize line endings in the search pattern to match whatever the file uses
def normalize_for_search(text):
    return text.replace('\r\n', '\n').replace('\r', '\n')

content_normalized = normalize_for_search(content)
old_normalized = normalize_for_search(old_block)

if old_normalized in content_normalized:
    # Find position in original content
    pos = content_normalized.find(old_normalized)
    # Count how many chars of original content correspond to normalized pos
    # We need to map back, so let's just work with normalized content
    new_content = content_normalized[:pos] + new_block.replace('\r\n', '\n').replace('\r', '\n') + content_normalized[pos + len(old_normalized):]
    
    with open(filepath, 'w', encoding='utf-8', newline='\n') as f:
        f.write(new_content)
    print("SUCCESS: Replaced broken code block in training.html")
else:
    # Try to find partial match for debugging
    lines_old = old_normalized.split('\n')
    for i, line in enumerate(lines_old):
        if line.strip() and line.strip() not in content_normalized:
            print(f"MISMATCH at line {i}: {repr(line.strip()[:80])}")
            break
    else:
        print("All individual lines found but combined block not found")
    print("FAILED: Could not find the target block")
