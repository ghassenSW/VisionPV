import os
import base64
import io
import time
import json
from dotenv import load_dotenv
from PIL import Image
from pdf2image import convert_from_path
from mistralai import Mistral
from google import genai
from google.genai import types

load_dotenv()

# --- CONFIGURATION ---
gemini_api_key = os.getenv("GEMINI_API_KEY")
if not gemini_api_key:
    raise ValueError("GEMINI_API_KEY is missing from environment variables")
gemini_client = genai.Client(api_key=gemini_api_key)

api_key = os.getenv("MISTRAL_API_KEY")
if not api_key:
    raise ValueError("MISTRAL_API_KEY is missing from environment variables")

client = Mistral(api_key=api_key)

def calculate_age_from_dates(birth_date, Date_du_PV):
    from datetime import datetime
    try:
        # Parse birth date
        if isinstance(birth_date, str):
            if '/' in birth_date:
                birth = datetime.strptime(birth_date, '%d/%m/%Y')
            elif '-' in birth_date:
                birth = datetime.strptime(birth_date, '%Y-%m-%d')
            else:
                return None
        else:
            return None
        
        # Parse accident date
        if isinstance(Date_du_PV, str):
            if '/' in Date_du_PV:
                accident = datetime.strptime(Date_du_PV, '%d/%m/%Y')
            elif '-' in Date_du_PV:
                accident = datetime.strptime(Date_du_PV, '%Y-%m-%d')
            else:
                return None
        else:
            return None
        
        birth_year = birth.year
        birth_month = birth.month
        birth_day = birth.day
        
        accident_year = accident.year
        accident_month = accident.month
        accident_day = accident.day
        age = accident_year - birth_year
        if accident_month < birth_month:
            age -= 1
        elif accident_month == birth_month and accident_day < birth_day:
            age -= 1
        
        return age
        
    except Exception as e:
        print(f"Error calculating age: {e}")
        return None

def prepare_vision_image_pil(pdf_path):
    """Converts PDF Page 1 into a fast-process PIL Image for Gemini Vision."""
    print(f"Étape 1 : Préparation de l'en-tête (Page 1)...")
    pages = convert_from_path(pdf_path, 200, first_page=1, last_page=1)
    img = pages[0]
    
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    
    width, height = img.size
    
    target_width = 700
    target_height = int(target_width * (height / width))
    
    if target_height > 1000:
        target_height = 800
        
    img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
    return img

def run_vision_step(img_pil):
    """Vision Module using Gem2ni Flash (Optimisé pour Vision+JSON)"""
    print("Étape 2 : Lancement de l'analyse Vision (Gemini 1.5 pro)...")
    prompt = """Tu es un expert en lecture de documents administratifs tunisiens. Analyse l'image de ce Procès-Verbal et extrais UNIQUEMENT les deux champs suivants dans un format JSON strict, sans aucun texte d'introduction ni de conclusion.
    Instructions d'extraction :
    Référence : Repère la mention MANUSCRITE (écrite à la main) qui suit le motif visuel de chiffres séparés par des étoiles (exemple : 03*06*2021) (sans espace). Tu dois extraire la valeur exacte en conservant impérativement les étoiles * et les chiffres. Ne confonds pas cette valeur avec les numéros de PV imprimés ou les numéros de page.
    Date_Depot : Localise l'ancre textuelle 'F.T.U.S.A.' et le mot 'ARRIVEE' figurant dans un tampon rectangulaire.
    Extrais la date figurant dans ce tampon (ex: '01 JUIN 2021').
    Convertis impérativement cette date au format numérique JJ/MM/AAAA (ex: '01/06/2021').
    
    Réponds UNIQUEMENT avec l'objet JSON :
    { "Référence": "...", "Date_Depot": "..." }"""

    try:
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt, img_pil],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            )
        )
        vision_output = response.text
        print("-> Analyse Vision (En-tête) réussie.")
        return json.loads(vision_output)
    except Exception as e:
        print(f"Erreur lors de l'appel Vision Gemini : {str(e)}")
        return None

def run_text_step(truncated_text, ref_ftusa, date_depot):
    """Text Module: Logic-heavy narrative analysis using Mistral Large 3"""
    
    prompt = f"""
    Vous êtes un expert en analyse de rapports d'accidents tunisiens (PV). 
    Vous allez recevoir un texte OCR ainsi que deux valeurs déjà extraites par un module de vision de haute précision.

    ### MÉTHODOLOGIE DE RÉFLEXION OBLIGATOIRE (CHAIN-OF-THOUGHT) :
    Avant d'extraire les valeurs finales, vous devez impérativement utiliser les champs `_reasoning_...` au début du JSON pour :
    1. Comprendre la dynamique de l'accident (qui fait quoi).
    2. Citer les passages exacts du texte justifiant vos choix pour les causes, les assurances et les victimes.
    3. Filtrer explicitement les victimes (exclure formellement les personnes indemnes) avant de les extraire.

    ### RÈGLE CRUCIALE : DONNÉES DÉJÀ EXTRAITES (NE PAS CHERCHER) :
    Les deux valeurs suivantes sont DÉFINITIVES. Ne les cherchez pas dans le texte OCR. Vous devez les recopier MOT À MOT dans le JSON final, sans modifier un seul caractère, même si le format paraît inhabituel :
    - Référence FTUSA à insérer : {ref_ftusa}
    - Date du dépôt du PV à insérer : {date_depot}

    ### INSTRUCTIONS POUR LE RESTE DE L'EXTRACTION (À CHERCHER DANS L'OCR) :
    1. **N° du PV** : Identifiez le numéro situé dans l'en-tête administratif, au tout début du document (souvent parmi les toutes premières lignes de texte). Cherchez impérativement le numéro qui suit ou accompagne les mots arabes "رقم" ou "عدد" (ex: 21.5.11).
    2. **Date du PV** : Cherchez la date située sur la première page, souvent à côté de "بتاريخ" près du numéro de PV.
    3. **Date d'Accident** : Cherchez dans le récit des faits commençant par "جد الحادث jour...". Format JJ/MM/AAAA.
    4. **Causes de sinistre** : (LOGIQUE PAR ÉTAPES) :
        Étape A : Identifiez d'abord l'infraction ou le problème technique décrit dans le récit du PV (ex: un pneu a éclaté, le conducteur a grillé un feu, etc.).
        Étape B : Recherchez dans la liste ci-dessous le terme qui correspond le mieux à cette réalité.
        Étape C : Si aucune cause spécifique ne correspond parfaitement, utilisez par défaut "Ne pas prendre les précautions nécessaires" (si c'est une erreur humaine) ou "Panne mécanique / technique" (si c'est un problème véhicule).
        * LISTE OBLIGATOIRE (Sélectionnez une seule valeur exacte) :  
            Marcher sur la chaussé
            Stationnement innaproprié
            Dépassement interdit
            Excès de vitesse
            Non respect de la priorité
            Téléphone portable au volant
            Ne pas prendre les précautions nécessaires
            Non respect des signalisations de l'agent  de Police de la circulation
            Non respect de la distance de sécurité
            Non respect des signalisations
            Non respect du panneau "céder le passage"
            Sortie (soudaine) de la route/chaussée /pavé
            Non mentionné / Non déterminé
            Panneau "Attention Travaux" non affiché
            Ne pas signaler "véhicule en panne"
            Nouveau en conduite
            Panne technique
            Ne pas prendre les précautions nécessaires lors du dépassement au rond point "céder le passage"
            Véhicule non destiné pour le transport des marchandises
            Non respect des feux de signalisations
            Interdiction de circuler des poids lourds
            Conduite sans assurance + sans permis de conduire
            Acte de violence
            Chute du / des piéton(s)
            Panne mécanique / technique
            Arrêt innaproprié
            Défaut d'attention
            accidents en chaine
            Changer de direction
            Collision par l'arrière
            Chutes sur la route
            Passage à niveau
            Rouler dans un sens interdit
            Vitesse réduite
            Circulation sur trottoir
            Circulation sur passage piétons
            Infraction routière
            Conduire en état d'ébriété
            Conduire en état de fatigue
            Rouler sans lumière la nuit
            Fraude
            Explosion d'une roue
            Route glissante
    5. **Nom du poste / Délégation** : Identifiez le nom géographique principal (la ville ou région) en analysant les en-têtes administratifs situés en haut à droite de chaque page. Ce nom se trouve généralement à la fin d'une ligne hiérarchique, souvent précédé de la particule "ب" (en/à).
    Exemples de structures à repérer :
    "... لحوادث المرور بمنوبة" → extraire "Manouba".
    "منطقة الحرس الوطني بقابس" → extraire "Gabès".
    Comme ces en-têtes se répètent sur toutes les pages, utilisez la page la plus nette pour confirmer. Inscrivez ce nom unique dans les deux champs "Nom du poste" et "Délégation".
    6. **Identification de l'Assurance** : Identifiez la compagnie d'assurance et transcrivez-la en utilisant uniquement les noms de la liste officielle ci-dessous.
    RÈGLE CRUCIALE : La compagnie AMI (Assurances Mutuelles Ittihad / أمي) doit impérativement être écrite "BNA Assurances".
    LISTE AUTORISÉE : Vous devez choisir l'un de ces noms exacts :
    Assurance Biat, Astrée, At-Takafulia, BH Assurance, BNA Assurances, BUAT, CARTE, COMAR, El Amana Takaful, GAT, Groupe CTAMA, Inconnue, LLoyd Tunisien, MAE, Maghrébia, Non assuré, Propriété de l'état, STAR, Zitouna Takaful.
    LOGIQUE DE MAPPING :
    "بيات" / "BIAT" → Assurance Biat
    "أستري" / "ASTRÉE"  → Astrée
    "التكافلية" / "TAKAFULIA" → At-Takafulia
    "بي هاش" / "BH" → BH Assurance
    "أمي" / "AMI" / "Ittihad" → BNA Assurances
    "بوات" / "BUAT" → BUAT
    "كارط" / "CARTE" → CARTE
    "كومار" / "COMAR" → COMAR
    "الأمانة" / "AMANA" → El Amana Takaful
    "قات" / "GAT" → GAT
    "كتاما" / "CTAMA" → Groupe CTAMA
    "الليد" / "اللويد" / "LLOYD" → LLoyd Tunisien
    "م أ إ" / "MAE" → MAE
    "المغاربية" / "MAGHRÉBIA" → Maghrébia
    "ستار" / "STAR" → STAR
    "الزيتونة" / "ZITOUNA" → Zitouna Takaful
    CAS PARTICULIERS :
    Si l'information est absente ou introuvable : Inconnue.
    Si le texte indique "غير مؤمنة" : Non assuré.
    Si le véhicule appartient à l'État (ex: plaque rouge, mention "ملك الدولة") : Propriété de l'état.

    ### LOGIQUE PRÉCISE POUR LES VICTIMES :
    7. **Sélection des victimes** : Incluez UNIQUEMENT les personnes ayant subi des dommages corporels. Vérifiez la section "الأضرار البدنية" et les compteurs "عدد الجرحى" / "عدد القتلى". Si une personne est indemne, ne l'ajoutez pas au JSON.
    8. **Âge et Date de Naissance des victimes (RÈGLE OBLIGATOIRE)** : 
       - **PRIORITÉ 1 (LA PLUS IMPORTANTE)** : Recherchez SYSTÉMATIQUEMENT et EN PREMIER la date de naissance dans le document en utilisant les mots-clés arabes suivants :
         * "مولود في" (né le)
         * "مولود بتاريخ" (né à la date)
         * "تاريخ الولادة" (date de naissance)
         * "ولد في" (né en)
       - Si vous trouvez une date de naissance, extrayez-la au format JJ/MM/AAAA et mettez-la dans le champ "Date naissance victime X".
       - **PRIORITÉ 2 (SEULEMENT SI DATE DE NAISSANCE NON TROUVÉE)** : Si la date de naissance n'est PAS disponible, mais que l'âge est écrit EXPLICITEMENT dans le PV (ex: "34 ans", "عمره 34 سنة"), extrayez-le et mettez-le dans le champ "Age victime X".
       - **IMPORTANT** : Cherchez TOUJOURS la date de naissance en premier. N'extrayez l'âge que si vous ne trouvez absolument pas la date de naissance.
       - Ne tentez PAS de calculer l'âge vous-même. Extrayez uniquement les informations présentes dans le document.
    9. **Séparation des Noms et Prénoms** : Procédez à l'extraction sélective des noms et prénoms selon une logique binaire. Extrayez exclusivement le premier segment de l'identité complète pour le champ 'Prénom' et le dernier segment pour le champ 'Nom'.
    Règle d'exclusion : Ignorez systématiquement les patronymes intermédiaires, le nom du père, ainsi que la particule de filiation 'ben' (بن) ou 'bin'.
    Format de sortie : Effectuez une transcription phonétique impérativement en français (alphabet latin). L'usage de caractères arabes dans le JSON final est strictement interdit.
    Exemple : "محمد بن شادلي منصوري" doit devenir Prénom: Mohamed, Nom: Mansouri.
    10. **Catégorisation de l'État Social (MAPPING)** : 
        - **Fonctionnaire Public** : État/Secteur public (Enseignant, Policier, Militaire).
        - **Sans emploi** : Chômeur, Femme au foyer, Étudiant, Élève, Retraité, Enfant.
        - **Profession libérale** : Secteur privé, Ouvrier, Journalier, Commerçant, Agriculteur, Chauffeur.
    11. **Type de véhicule (MAPPING)** : Vous devez impérativement faire correspondre le véhicule identifié à l'une des catégories suivantes, et UNIQUEMENT à celles-ci :
        - Ambulance, Bus, Camion, Location, Louage, Motocyclette (inférieur à 50cm3), Motocyclette (supérieur à 125cm3), Motocyclette légère (50-125 cm³), Métro, Objets impliqués, Remorquage, Remorque et semi remorque, Taxi Individuel, Taxi collectif, Tracteur, Train, Tricycle à moteur, Véhicule administratif, Véhicule de transport rural, Vélo ordinaire, camionnette, voiture.
    12. **Poste de Police / Garde Nationale** : Identifiez l'organisme ayant rédigé le PV en analysant l'en-tête (en haut à droite). Vous devez effectuer un choix binaire obligatoire :
        - Si vous voyez les mots "الحرس الوطني", inscrivez exclusivement : "Garde Nationale".
        - Si vous voyez les mots "الأمن الوطني" ou "الشرطة", inscrivez exclusivement : "Poste de Police".
        Interdiction : Ne créez aucune autre catégorie et ne laissez pas ce champ vide.

    ### RÈGLES DE FORMATAGE :
    - Langue : FRANÇAIS exclusivement.
    - Causes de sinistre : Très bref (5-7 mots). Uniquement le fait générateur.
    - Compagnie : Nom commercial en MAJUSCULES. **Si le texte mentionne "AMI" ou "أمي", écrivez "BNA Assurance"**. Si "غير مؤمنة" -> "Non assuré".
    - N° Imm : MAJUSCULES. Supprimez impérativement TOUS les espaces. Si immatriculation arabe (ex: "رقم 6327 تونس 18"), convertissez en "NumTUSerie" (ex: "6327TU18"). Pour les numéros de châssis, donnez la chaîne brute sans espaces ni étoiles. Si absent -> "".
    - Type de véhicule : **CHOIX STRICT** dans la liste définie au point n°11. Ne créez aucune autre catégorie.
    - Etat social : CHOIX STRICT : "Fonctionnaire Public", "Sans emploi" ou "Profession libérale".
    - Victimes : Sexe ("Homme"/"Femme"), Type ("Blessé"/"Décédé"), Catégorie ("Conducteur"/"Piéton"/"Passager").

    ### STRUCTURE JSON ATTENDUE :
    {{
        "_reasoning_contexte": "1. Résumez la dynamique de l'accident : qui conduisait quoi, dans quelle direction, et que s'est-il passé ?",
        "_reasoning_causes": "2. Citez le passage précis traitant de l'infraction/panne, puis déduisez-en formellement le terme STRICT dans la liste officielle.",
        "_reasoning_vehicules": "3. Listez les véhicules impliqués. Pour chaque assurance trouvée, appliquez le mapping autorisé (ex: 'AMI' devient 'BNA Assurances').",
        "_reasoning_victimes": "4. Cherchez la rubrique des dégâts corporels. Comptez les blessés et les morts. Identifiez leur date de naissance ou âge. EXCLUEZ explicitement les personnes indemnes.",
        
        "Référence FTUSA": "{ref_ftusa}",
        "N° du PV": "Valeur extraite",
        "Date du dépôt du PV": "{date_depot}",
        "Date d'Accident": "JJ/MM/AAAA",
        "Date du PV": "JJ/MM/AAAA",
        "Poste de Police / Garde Nationale": "Poste de Police ou Garde Nationale",
        "Nom du poste": "Nom de la délégation en français",
        "Délégation": "Nom de la délégation en français",
        "Causes de sinistre": "Résumé ultra-concis",
        
        # pour chaque vehicule :
        "N° Imm 1": "...",
        "Compagnie 1": "...",
        "Type de véhicule 1": "CHOIX STRICT LISTE POINT 11",

        # pour chaque victime (UNIQUEMENT les blessés ou décédés) :
        "Type victime 1": "Blessé ou Décédé",
        "Prénom victime 1": "Prénom uniquement (en francais)",
        "Nom victime 1": "Nom uniquement (en francais)",
        "CIN victime 1": "8 chiffres",
        "Age victime 1": 0,  # Si âge explicite disponible
        "Date naissance victime 1": "JJ/MM/AAAA",  # Si seulement date de naissance disponible
        "Etat social victime 1": "Fonctionnaire Public, Sans emploi ou Profession libérale",
        "Catégorie victime 1": "Conducteur, Piéton ou Passager",
        "Sexe victime 1": "Homme ou Femme",

        "Total décédés": 0,
        "Total blessés": 0
    }}

    TEXTE OCR À ANALYSER :
    {truncated_text}
    """

    print("Appel Mistral Large 3 (Analyse du texte narratif)...")
    response = client.chat.complete(
        model="mistral-large-latest",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0
    )
    return json.loads(response.choices[0].message.content)

def process_pv(ocr_text, pdf_path):
    """Processes a single PV by combining Vision and Text extraction."""
    # 1. Start with Vision (with error handling)
    ref_ftusa = ""
    date_depot = ""
    
    try:
        print("Tentative d'extraction avec Vision (Aplatissement en Capture d'écran)...")
        img_pil = prepare_vision_image_pil(pdf_path)
        
        print("--> Analyse Vision...")
        data = run_vision_step(img_pil)
        
        ref_ftusa = data.get("Référence", "") if data else ""
        date_depot = data.get("Date_Depot", "") if data else ""
            
        print(f"✅ Vision OK: Référence={ref_ftusa}, Date_Depot={date_depot}")
    except Exception as vision_error:
        print(f"⚠️ Erreur Vision (non-bloquante): {vision_error}")
        print("⏭️ Passage direct à l'étape LLM avec champs Vision vides...")
        ref_ftusa = ""
        date_depot = ""
    
    # 2. Quota Safety Gap
    if ref_ftusa or date_depot:
        print("Pause finale de synchronisation API (15s)...")
        time.sleep(15)

    # 3. Process Text with Large 3
    # Inject Vision results into the Text prompt
    data_final = run_text_step(
        ocr_text, 
        ref_ftusa, 
        date_depot
    )

    # 4. Final Verification: Ensure Vision data is in the final JSON
    data_final["Référence FTUSA"] = ref_ftusa
    data_final["Date du dépôt du PV"] = date_depot
    
    if not ref_ftusa:
        print("⚠️ WARNING: Référence FTUSA est vide (vision step échouée)")
    if not date_depot:
        print("⚠️ WARNING: Date du dépôt du PV est vide (vision step échouée)")
    
    # 5. Calculate ages from birth dates if needed
    Date_du_PV = data_final.get("Date du PV", "").strip()
    print("\nCalcul des âges des victimes...")
    
    for i in range(1, 11):  # Check up to 10 victims
        age_key = f"Age victime {i}"
        birth_key = f"Date naissance victime {i}"
        
        # If birth date exists
        if birth_key in data_final and data_final[birth_key]:
            birth_date = str(data_final[birth_key]).strip()
            current_age = data_final.get(age_key, 0)
            
            # Convert empty string or None to 0
            if current_age == "" or current_age is None:
                current_age = 0
            
            # Calculate age if not already present or is 0
            if not current_age or current_age == 0:
                if birth_date and Date_du_PV:
                    calculated_age = calculate_age_from_dates(birth_date, Date_du_PV)
                    if calculated_age is not None:
                        data_final[age_key] = calculated_age
                        print(f"  Victime {i}: Âge calculé = {calculated_age} ans (né le {birth_date})")
                    else:
                        print(f"  Victime {i}: Erreur de calcul d'âge (dates invalides)")
                else:
                    print(f"  Victime {i}: Données manquantes pour calcul d'âge")
            else:
                print(f"  Victime {i}: Âge déjà présent = {current_age} ans")
                
            # Remove birth date from final output
            if birth_key in data_final:
                del data_final[birth_key]
            
    return data_final