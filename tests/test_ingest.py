import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / 'tools'))
from ingest import split_questions

def tot(qs): return sum(q['points'] or 0 for q in qs)

T_17863 = "ΘΕΜΑ 2Ο\n\n2.1. Στο νόμο του Coulomb, η σταθερά k:\nα. είναι καθαρός αριθμός.\n\n(Μονάδες 5)\n\n2.2. Να γράψετε ΣΩΣΤΟ ή ΛΑΘΟΣ\n1. Το φορτίο\n2. Τα άτομα\n(Μονάδες 10)\n\n2.3. Να γράψετε τα γράμματα α, β\nΣτήλη Α Στήλη Β\n(Μονάδες 10)"
T_19657 = "Θέμα 2ο\n\n2.1 Ποια μονάδα;\n\nΜονάδες: 04\n\n2.2 Εμφανίζεται ένταση;\nα. Διπλασιάζεται\n\nΜονάδες: 06\n\n2.3 Να γίνει η συμπλήρωση του πίνακα\n(Ένδειξη έντασης ρεύματος) Μονάδες: 15"
T_18258 = "Θέμα 4o\n\n4.1 Στο παρακάτω κύκλωμα\nΝα υπολογίσετε:\nα) τη συνολική χωρητικότητα\nΜονάδες 6\nβ) το συνολικό φορτίο Qολ.\nΜονάδες 9\n\n4.2 Ένας επίπεδος πυκνωτής\nα) τη χωρητικότητα C\nΜονάδες 5\nβ) το φορτίο Q\nΜονάδες 5"
T_20677 = "Θέμα 4ο\n\nΔίνεται το παρακάτω κύκλωμα με Ε = 5 Volt.\nΝα υπολογιστούν:\nα) Η ολική αντίσταση\nβ) Η ένταση Ι.\n\nΜονάδες 25"
T_28051 = "ΘΕΜΑ 2\n\n1) Να χαρακτηρίσετε τις προτάσεις\nα. Η αγωγιμότητα\n(Μονάδες 6)\n\n2) Να αντιστοιχίσετε\n1 Ηλεκτρική Αντίσταση α. G\n(Μονάδες 9)\n\n3) Να αντιστοιχίσετε το Σύμβολο\n(Μονάδες 10)"
T_22078 = "Θέμα 2ο\n\n2.1 Να χαρακτηρίσετε\nα. ...\nΜονάδες 15\n\n2.2 Να επιλέξετε την ορθή απάντηση:\n\n2.2.1 Αν η τάση τροφοδοσίας\nα. κάτι\nΜονάδες 5\n\n2.2.2 Για το κύκλωμα\nα. κάτι\nΜονάδες 5"

def test_trailing_dot_and_parenthesised_points():
    qs = split_questions(T_17863); assert [q['code'] for q in qs] == ['2.1', '2.2', '2.3'] and tot(qs) == 25
def test_colon_points_with_leading_zero():
    qs = split_questions(T_19657); assert [q['points'] for q in qs] == [4, 6, 15]
def test_subparts_points_are_summed():
    qs = split_questions(T_18258); assert [q['points'] for q in qs] == [15, 10]
def test_no_numbering_single_question():
    qs = split_questions(T_20677); assert len(qs) == 1 and qs[0]['points'] == 25
def test_paren_numbering_uses_theme_number():
    qs = split_questions(T_28051); assert [q['code'] for q in qs] == ['2.1', '2.2', '2.3'] and tot(qs) == 25
def test_nested_codes():
    qs = split_questions(T_22078); assert [q['code'] for q in qs] == ['2.1', '2.2', '2.2.1', '2.2.2'] and tot(qs) == 25

def test_numbers_at_line_start_are_not_questions():
    qs = split_questions("Θέμα 2ο\n\n2.1 Υπολογίστε\n5.5 V είναι η τάση\nΜονάδες 25"); assert [q['code'] for q in qs] == ['2.1']

def test_part_points_followed_by_total_not_double_counted():
    t = "ΘΕΜΑ 2Ο\n\n2.1. Νόμος\n1. α (Μονάδες 4)\n2. β (Μονάδες 2)\n3. γ (Μονάδες 4)\n(Μονάδες 10)\n\n2.2. Σ/Λ\n(Μονάδες 10)\n\n2.3. Επιλογή\n(Μονάδες 5)"
    qs = split_questions(t); assert [q['points'] for q in qs] == [10, 10, 5]
def test_total_with_colon_after_parts():
    qs = split_questions("Θέμα 4ο\n\n4.1 κάτι\nα. (Μονάδες 05)\nβ. (Μονάδες 05)\nΜονάδες: 10\n\n4.2 άλλο\nα. (Μονάδες 07)\nβ. (Μονάδες 08)\nΜονάδες:15")
    assert [q['points'] for q in qs] == [10, 15]
def test_heading_alone_on_line():
    qs = split_questions("Θέμα 2ο\n\n2.1 Σ/Λ\nΜονάδες 15\n\n2.2\n\nα) Τι είναι;\nΜονάδες 5\nβ) Γιατί;\nΜονάδες 10")
    assert [q['code'] for q in qs] == ['2.1', '2.2'] and [q['points'] for q in qs] == [15, 15]
def test_duplicate_codes_made_unique():
    qs = split_questions("Θέμα 2ο\n2.1 α\nΜονάδες 10\n2.1 β\nΜονάδες 15"); assert len({q['code'] for q in qs}) == 2

def test_global_theme_total_not_added_to_last_question():
    t = "Θέμα 4ο\n\n4.1 α. (Μονάδες 04)\n4.2 β. (Μονάδες 08)\n4.3 γ. (Μονάδες 08)\n4.4 δ. (Μονάδες 05)\n\nΜονάδες: 25"
    qs = split_questions(t); assert [q['points'] for q in qs] == [4, 8, 8, 5]
def test_global_total_with_part_totals_36470_style():
    t = "Θέμα 4ο\n\n4.1 κάτι\nα. (Μονάδες 05)\nβ. (Μονάδες 05)\nΜονάδες: 10\n\n4.2 άλλο\nα. (Μονάδες 07)\nβ. (Μονάδες 08)\nΜονάδες:15"
    assert sum(q['points'] for q in split_questions(t)) == 25

def test_own_text_cuts_at_next_heading_and_summary():
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / 'tools'))
    from suggest_links import own_text, norm
    full = "τέλος προηγούμενης\n4.1.2. Ένταση πεδίου\nκείμενο έντασης\n4.1.3. Δυναμικές γραμμές\nάλλο\nΑνακεφαλαίωση\nερωτήσεις"
    t = own_text(full, '4.1.2', '4.1.3'); assert 'έντασης' in t and 'γραμμές' not in t and 'προηγούμενης' not in t
    t3 = own_text(full, '4.1.3', None); assert 'άλλο' in t3 and 'ερωτήσεις' not in t3
    assert norm('Ηλεκτρικού ΠΕΔΙΟΥ') == ['ηλεκτρ', 'πεδιου']

from classify import qtype, annotate
def test_qtypes():
    assert qtype('2.1 Να χαρακτηρίσετε ... Σωστό ... Λάθος') == 'true_false'
    assert qtype('2.2 Να αντιστοιχίσετε τους αριθμούς 1,2 της στήλης Α') == 'matching'
    assert qtype('2.3 ... ταιριάζει στο αντίστοιχο κενό: α. ______ και ____') == 'fill'
    assert qtype('2.1 Η σταθερά k:\nα. είναι ένα\nβ. είναι δύο\nγ. είναι τρία\nδ. τέσσερα') == 'mcq'
    assert qtype('4.1 Να υπολογίσετε την αντίσταση', '4') == 'problem'
    assert qtype('2.2 Να εξηγήσετε τι είναι το πεδίο') == 'development'
def test_image_from_text_and_page():
    qs = [{'code': '4.1', 'text': '4.1 Στο κύκλωμα του σχήματος να βρείτε'}, {'code': '4.2', 'text': '4.2 Ένας πυκνωτής'}]
    r = annotate(qs, 'Θέμα 4ο\n4.1 Στο κύκλωμα του σχήματος να βρείτε\n\x0c4.2 Ένας πυκνωτής', {1}); assert [q['has_image'] for q in r] == [1, 1]
    r = annotate([{'code': '2.1', 'text': '2.1 Τι είναι'}], 'Θέμα 2ο\n2.1 Τι είναι', set()); assert r[0]['has_image'] == 0
