"""Bounded full-clause constructions; no free substring entailment.

Callers must already verify verbatim evidence and require coverage of the whole
source clause. Unknown constructions intentionally remain unverified.
"""
import re

SYMPTOMS = {
    'abdominal_pain': r'(?:abdominal pain|lower abdominal pain|abdominal cramping|lower abdominal cramps|lower abdominal aching)',
    'change_in_bowel_habit': r'(?:change in bowel habits?|changes in bowel habits|loose stools|constipation)',
    'rectal_bleeding': r'(?:(?:visible )?blood in (?:the )?stool|rectal bleeding)',
    'weight_loss': r'(?:unintentional )?weight loss',
}
QUALIFIER = r'(?:(?:intermittent|occasional|episodes of) )?'
DURATION = r'(?: (?:persists?|for (?:one|three|\d+) months?|since (?:spring|summer|autumn|winter)|before defaecation))?'
ATOM = '(?:' + '|'.join(SYMPTOMS.values()) + ')'


def symptom_states(kind, clause):
    result = set()
    term = SYMPTOMS.get(kind)
    if not term:
        return result
    # Each member is independently asserted; grammar consumes the entire clause.
    positive = rf'{QUALIFIER}{ATOM}(?: and {QUALIFIER}{ATOM})*{DURATION}'
    if re.fullmatch(positive, clause):
        if re.search(rf'(?<!\w){term}(?!\w)', clause):
            result.add(('present', 'current'))
    negative_atom = rf'(?:{ATOM}|unusual fatigue|visible bleeding)'
    if re.fullmatch(rf'no {negative_atom}(?:(?:, | or ){negative_atom})*', clause):
        if re.search(rf'(?<!\w){term}(?!\w)', clause):
            result.add(('absent', 'current'))
    # Bowel variation with an explicitly localized cramp, not generic symptoms.
    if re.fullmatch(rf'bowel habits vary, with {QUALIFIER}{SYMPTOMS["abdominal_pain"]}', clause):
        if kind in {'change_in_bowel_habit', 'abdominal_pain'}:
            result.add(('present', 'current'))
    if kind == 'change_in_bowel_habit':
        if re.fullmatch(r'bowel movements (?:sometimes )?less frequent than previously', clause) or re.fullmatch(r'episodes of loose stools for (?:one|three|\d+) months?, normal stools in between', clause):
            result.add(('present', 'current'))
        if clause in {'regular bowel movements', 'regular bowel movements, no blood in stool'}:
            result.add(('absent', 'current'))
    if kind == 'rectal_bleeding':
        if re.fullmatch(r'(?:reports reddish blood on toilet paper twice|bright red blood with defaecation once)', clause):
            result.add(('present', 'current'))
        if clause in {'has not noticed blood in stool', 'regular bowel movements, no blood in stool'}:
            result.add(('absent', 'current'))
    if kind == 'weight_loss' and clause == 'no weight loss, good appetite':
        result.add(('absent', 'current'))
    # Resolution is explicitly attached to every named symptom in a closed list.
    if re.fullmatch(rf'previous {ATOM}(?: and {ATOM})* have resolved', clause):
        if re.search(rf'(?<!\w){term}(?!\w)', clause):
            result.add(('present', 'resolved'))
    return result


def investigation_state(clause):
    if re.fullmatch(r'colonoscopy completed(?: to the caecum with good visibility|: good visibility, examination to the caecum)?', clause):
        return 'completed'
    if re.fullmatch(r'(?:referral for colonoscopy made|colonoscopy referral made(?: to investigate symptoms)?)', clause):
        return 'referred'
    if clause == 'completion of the previous colonoscopy referral is uncertain':
        return 'status_unknown'
    return None
