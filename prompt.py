PROMPT_TEMPLATE = """\
Vous êtes un expert en analyse de rapports d'accidents tunisiens (PV). 
Vous allez recevoir un texte OCR extrait d'un document PDF. Votre tâche est d'extraire TOUTES les informations structurées directement depuis ce texte.

### MÉTHODE :
Raisonnez étape par étape en silence (dynamique de l'accident, causes, assurances, victimes réelles uniquement — excluez les indemnes). **Ne produisez aucun texte de raisonnement dans la sortie.** Le JSON final ne contient que les clés ci-dessous : `pv_info`, `vehicules`, `victimes`.

### INSTRUCTIONS D'EXTRACTION :
1. **Référence FTUSA** : {ref_ftusa_instruction}
2. **Date du dépôt du PV** : {date_depot_instruction}
3. **N° du PV** : Identifiez le numéro d'identification officiel du dossier.
Localisation : Ce numéro est situé à la fin du bloc administratif initial (juste après la désignation de l'unité, ex: "الفرقة الخامسة").
Détection par mots-clés : Cherchez le chiffre qui suit immédiatement les mentions "عدد :" (Nombre/Numéro) ou "رقم" (Chiffre/Numéro).
Logique d'extraction STRICTE : 
    - Vous devez extraire le numéro EXACTEMENT tel qu'il est écrit dans le document original, sans AUCUNE modification, conversion ou reformatage (conservez la ponctuation exacte : points, tirets, slashs, etc.). Ne tentez jamais d'adapter la valeur à un format de date.
    - Cas particulier (Numéro de page) : Dans les dossiers de plusieurs pages, si le numéro est écrit sous la forme "page / PV" (ex: 01/214, 02/214), ignorez le numéro de page et gardez uniquement le numéro du PV ("214").
Règle d'exclusion CRUCIALE : Ne prenez jamais un numéro écrit seul ou à la main tout en haut de la page (ex: "324") car c'est souvent une référence d'archive.
Exemples cibles :
    "عدد : 145" → "145"
    "محضر بحث عدد 205" → "205"
    "عدد : 01/214" → "214" (ici 01 est le n° de page)
4. **Date du PV** : Cherchez la date située sur la première page, souvent à côté de "بتاريخ" près du numéro de PV.
5. **Date d'Accident** : Cherchez dans le récit des faits commençant par "جد الحادث jour...". Format JJ/MM/AAAA.
6. **Lieu d'Accident / Délégation / Gouvernorat** : 
    - Lisez le contexte de la zone géographique de l'accident (rue, route nationale, point kilométrique, ou la rubrique "مكان الحادث").
    - Extrayez la formulation complète dans le champ "Lieu d'Accident" et traduisez-la TOUJOURS en français (ex: "Route Nationale 1", "Rue Habib Bourguiba"). L'arabe est strictement interdit.
    - À partir de ce lieu, déduisez LOGIQUEMENT la **Délégation** correspondante à cette zone géographique (en français, ex: "Sousse Médina", "La Marsa"...).
    - À partir de ce lieu ou de cette délégation, déduisez également LOGIQUEMENT le **Gouvernorat** dans lequel se trouve l'accident (en français, ex: "Sousse", "Tunis"...).
7. **Causes de sinistre** (CLASSIFICATION UNIQUE ET STRICTE) :
    - VOTRE MISSION : Vous devez agir comme un classifieur de données. Vous ne devez pas inventer de texte. Votre but est de faire correspondre le récit de l'accident à UNE SEULE ET UNIQUE VALEUR de la liste officielle ci-dessous.
- LOGIQUE DE DÉCISION (À SUIVRE DANS L'ORDRE) :
    Analyse des faits : Identifiez le "fait générateur" (l'élément qui a déclenché l'accident) dans le récit.
    Recherche de correspondance exacte : Parcourez la liste ci-dessous. Si une valeur correspond précisément à l'infraction citée (ex: l'alcool est mentionné -> "Conduire en état d'ébriété"), sélectionnez-la immédiatement.
    Gestion des causes multiples : Si plusieurs infractions sont citées, choisissez uniquement la cause principale (celle qui a provoqué l'impact).
    Priorité sur "عدم اخذ الاحتياطات" : Si le texte arabe cite "عدم اخذ الاحتياطات اللازمة إثناء السياقة" combiné à une autre action spécifique (ex: "و المداهمة من الخلف"), IGNOREZ "Ne pas prendre les précautions nécessaires" et extrayez TOUJOURS la cause la plus précise (dans cet exemple : "Collision par l'arrière").
    # Application des SOLUTIONS DE SECOURS (FALLBACKS) :
    # Si vous identifiez une erreur humaine mais qu'aucun terme de la liste n'est assez précis, utilisez obligatoirement : "Ne pas prendre les précautions nécessaires".
    # Si vous identifiez un problème sur le véhicule (freins, moteur, direction) sans plus de précision, utilisez obligatoirement : "Panne mécanique / technique".
    # Si le texte est totalement muet sur la cause ou contradictoire, utilisez obligatoirement : "Non mentionné / Non déterminé".
- RÈGLES CRUCIALES :
    INTERDICTION ABSOLUE de créer une nouvelle catégorie ou de modifier l'orthographe de la liste.
    UN SEUL CHOIX : Ne retournez pas plusieurs causes.
    COPIER-COLLER EXACT : La valeur dans le JSON doit être identique caractère par caractère à la liste ci-dessous.
- LISTE OFFICIELLE OBLIGATOIRE :
    Marcher sur la chaussé, Stationnement innaproprié, Dépassement interdit, Excès de vitesse, Non respect de la priorité, Téléphone portable au volant, Ne pas prendre les précautions nécessaires, Non respect des signalisations de l'agent de Police de la circulation, Non respect de la distance de sécurité, Non respect des signalisations, Non respect du panneau "céder le passage", Sortie (soudaine) de la route/chaussée /pavé, Non mentionné / Non déterminé, Panneau "Attention Travaux" non affiché, Ne pas signaler "véhicule en panne", Nouveau en conduite, Panne technique, Ne pas prendre les précautions nécessaires lors du dépassement au rond point "céder le passage", Véhicule non destiné pour le transport des marchandises, Non respect des feux de signalisations, Interdiction de circuler des poids lourds, Conduite sans assurance + sans permis de conduire, Acte de violence, Chute du / des piéton(s), Panne mécanique / technique, Arrêt innaproprié, Défaut d'attention, accidents en chaine, Changer de direction, Collision par l'arrière, Chutes sur la route, Passage à niveau, Rouler dans un sens interdit, Vitesse réduite, Circulation sur trottoir, Circulation sur passage piétons, Infraction routière, Conduire en état d'ébriété, Conduire en état de fatigue, Rouler sans lumière la nuit, Fraude, Explosion d'une roue, Route glissante.

8. **Nom du poste** : Identifiez le nom géographique principal (la ville ou région) en analysant les en-têtes administratifs situés en haut à droite de chaque page. Ce nom se trouve généralement à la fin d'une ligne hiérarchique, souvent précédé de la particule "ب" (en/à).
Exemples de structures à repérer :
"... لحوادث المرور بمنوبة" → extraire "Manouba" comme Nom du poste.
"منطقة الحرس الوطني بقابس" → extraire "Gabès" comme Nom du poste.
Comme ces en-têtes se répètent sur toutes les pages, utilisez la page la plus nette pour confirmer. Inscrivez uniquement ce nom dans le champ "Nom du poste".
9. **Identification de l'Assurance** : Identifiez la compagnie d'assurance et transcrivez-la en utilisant uniquement les noms de la liste officielle ci-dessous.
RÈGLE CRUCIALE : La compagnie AMI (Assurances Mutuelles Ittihad / أمي) doit impérativement être écrite "BNA Assurances".
LISTE AUTORISÉE : Vous devez choisir l'un de ces noms exacts :
Al Baraka Assurances, Assurance Biat, Assurance étrangère, Assurance militaire, Astrée, At-Takafulia, BH Assurance, BNA Assurances, BUAT, CARTE, COMAR, GAT, Groupe CTAMA, Inconnue, LLoyd Tunisien, MAE, Maghrébia, Non assuré, Propriété de l'état, STAR, Zitouna Takaful.
LOGIQUE DE MAPPING :
"بيات" / "BIAT" → Assurance Biat
"أستري" / "ASTRÉE"  → Astrée
"التكافلية" / "TAKAFULIA" → At-Takafulia
"بي هاش" / "BH" → BH Assurance
"أمي" / "AMI" / "Ittihad" → BNA Assurances
"بوات" / "BUAT" → BUAT
"كارط" / "CARTE" → CARTE
"كومار" / "COMAR" → COMAR
"البركة" / "BARAKA" → Al Baraka Assurances
"قات" / "GAT" → GAT
"كتاما" / "CTAMA" → Groupe CTAMA
"الليد" / "اللويد" / "LLOYD" → LLoyd Tunisien
"ت ت ت" / "تعاونية التأمين للتعليم" / "MAE" → MAE
"المغاربية" / "MAGHRÉBIA" → Maghrébia
"ستار" / "STAR" → STAR
"الزيتونة" / "ZITOUNA" → Zitouna Takaful
CAS PARTICULIERS :
Si l'information est absente ou introuvable : Inconnue.
Si le texte indique "غير مؤمنة" : Non assuré.
Si le véhicule appartient à l'État (ex: plaque rouge, mention "ملك الدولة") : Propriété de l'état.
Si le véhicule appartient à l'armée / militaire (ex: "جيش" ou "عسكرية") : Assurance militaire.
Si l'assurance est étrangère / issue d'un autre pays (ex: "أجنبية") : Assurance étrangère.

### LOGIQUE PRÉCISE POUR LES VICTIMES :
10. **Sélection des victimes** : Incluez UNIQUEMENT les personnes ayant subi des dommages corporels. Vérifiez la section "الأضرار البدنية" et les compteurs "عدد الجرحى" / "عدد القتلى". Si une personne est indemne, ne l'ajoutez pas au JSON.
11. **Âge et Date de Naissance des victimes (RÈGLE OBLIGATOIRE)** : 
    - **PRIORITÉ 1 (LA PLUS IMPORTANTE)** : Recherchez SYSTÉMATIQUEMENT et EN PREMIER la date de naissance dans le document en utilisant les mots-clés arabes suivants :
        * "مولود في" (né le)
        * "مولود بتاريخ" (né à la date)
        * "تاريخ الولادة" (date de naissance)
        * "ولد في" (né en)
    - Si vous trouvez une date de naissance, extrayez-la au format JJ/MM/AAAA et mettez-la dans le champ "Date naissance victime X".
    - **PRIORITÉ 2 (SEULEMENT SI DATE DE NAISSANCE NON TROUVÉE)** : Si la date de naissance n'est PAS disponible, mais que l'âge est écrit EXPLICITEMENT dans le PV (ex: "34 ans", "عمره 34 سنة"), extrayez-le et mettez-le dans le champ "Age victime X".
    - **IMPORTANT** : Cherchez TOUJOURS la date de naissance en premier. N'extrayez l'âge que si vous ne trouvez absolument pas la date de naissance.
    - Ne tentez PAS de calculer l'âge vous-même. Extrayez uniquement les informations présentes dans le document.
12. **Séparation des Noms et Prénoms** : Procédez à l'extraction sélective des noms et prénoms. Vous devez extraire le prénom complet dans le champ 'Prénom' et le nom de famille dans le champ 'Nom'.
RÈGLE CRUCIALE POUR LES PRÉNOMS COMPOSÉS : En arabe, de nombreux prénoms sont composés (ex: "محمد علي", "محمد أمين", "فاطمة الزهراء", "سيف الدين"). **Ne séparez jamais un prénom composé !** Le deuxième mot (ex: "علي" ou "أمين") appartient au prénom et ne doit SURTOUT PAS être extrait comme nom de famille. 
Règle d'exclusion : Ignorez systématiquement les noms intermédiaires (le nom du père) et la particule de filiation "بن" ou "bin".
Format de sortie : Effectuez une transcription phonétique impérativement en français (alphabet latin). L'usage de caractères arabes dans le JSON final est strictement interdit.
Exemples : 
- "محمد بن شادلي منصوري" → Prénom: Mohamed, Nom: Mansouri.
- "محمد علي الطرابلسي" → Prénom: Mohamed Ali, Nom: Trabelsi.
- "سيف الدين بن محمود" → Prénom: Seifeddine, Nom: Mahmoud.
13. **Catégorisation de l'État Social (MAPPING)** : 
    - **Fonctionnaire Public** : État/Secteur public (Enseignant, Policier, Militaire).
    - **Sans emploi** : Chômeur, Femme au foyer, Étudiant, Élève, Retraité, Enfant.
    - **Profession libérale** : Secteur privé, Ouvrier, Journalier, Commerçant, Agriculteur, Chauffeur.
14. **Type de véhicule (MAPPING)** : Vous devez impérativement faire correspondre le véhicule identifié à l'une des catégories suivantes, et UNIQUEMENT à celles-ci :
    - Louage, Taxi Individuel, Véhicule rapide d’intervention, Motocyclette légère (50-125 cm³), Vélo ordinaire ,Train, Engin de travaux ,Tricycle à moteur ,Motocyclette (supérieur à 125cm3) ,Quadricycles à moteur , Taxi collectif ,Véhicule administratif ,Auto Ecole , Location ,Véhicule de transport rural ,Véhicule touristique privé (transport  personnel) ,Taxi Touristique, Trottinette ,Autobus public (transport régional) - transport personnel, Motocyclette (supérieur à 50cm3) - Administratif, Autobus TCV  (transport en commun de voyageurs), Ambulance, Objets impliqués, Bus, Motocyclette (inférieur à 50cm3), voiture, Métro, véhicules Electrique, Remorquage, Remorque et semi remorque, Tracteur, véhicules, Camion
15. **Poste de Police / Garde Nationale** : Identifiez l'organisme ayant rédigé le PV en analysant l'en-tête (en haut à droite). Vous devez effectuer un choix binaire obligatoire :
    - Si vous voyez les mots "الحرس الوطني", inscrivez exclusivement : "Garde Nationale".
    - Si vous voyez les mots "الأمن الوطني" ou "الشرطة", inscrivez exclusivement : "Poste de Police".
    Interdiction : Ne créez aucune autre catégorie et ne laissez pas ce champ vide.
    16. **Conducteurs des véhicules** : Pour chaque véhicule impliqué, identifiez le conducteur. Extrayez son numéro de CIN, ainsi que son prénom et son nom combinés dans un seul champ (en appliquant la règle de transcription en français du point 12).
    17. **Lien Victime - Véhicule** : Le champ `vehicule_id` d'une victime fait référence à l'ID du véhicule. Vous devez lier une victime à un véhicule UNIQUEMENT si celle-ci en est le conducteur. Si la victime est un "Passager" ou un "Piéton", vous DEVEZ attribuer la valeur `null` à ce champ.

    ### RÈGLES DE FORMATAGE :
- Langue : FRANÇAIS exclusivement.
- Causes de sinistre : Très bref (5-7 mots). Uniquement le fait générateur.
- Compagnie : Nom commercial en MAJUSCULES. **Si le texte mentionne "AMI" ou "أمي", écrivez "BNA Assurance"**. Si "غير مؤمنة" -> "Non assuré".
- N° Imm : MAJUSCULES. Supprimez impérativement TOUS les espaces. TRÈS IMPORTANT : N'insérez les lettres "TU" au milieu du numéro QUE SI le mot "تونس" ou les lettres "TU" sont explicitement écrits entre les chiffres dans le texte source (ex: "رقم 6327 تونس 18" -> "6327TU18"). Si la plaque est formatée sans mention explicite du pays (ex: "11-152274" ou "152274-11"), conservez sa ponctuation d'origine sans inventer ni forcer l'ajout du "TU" (ex: "11-152274" doit rester "11-152274"). Cas particulier "Régime Suspensif" : Si vous trouvez "ن ت" avec un numéro, convertissez-le en "RS" suivi du numéro sans espace (ex: "123456 ن ت" -> "RS123456"). Pour les numéros de châssis, donnez la chaîne brute sans espaces ni étoiles. Si absent -> "".
- Type de véhicule : **CHOIX STRICT** dans la liste définie au point n°14. Ne créez aucune autre catégorie.
- Etat social : CHOIX STRICT : "Fonctionnaire Public", "Sans emploi" ou "Profession libérale".
- Victimes : Sexe ("Homme"/"Femme"), Type ("Blessé"/"Décédé"), Catégorie ("Conducteur"/"Piéton"/"Passager").

### STRUCTURE JSON ATTENDUE :
{{{{
"pv_info": {{
        "Référence FTUSA": "Valeur extraite (chiffres*étoiles) ou ''",
        "N° du PV": "Valeur numérique (ex: 21.5.09)",
        "Date du dépôt du PV": "JJ/MM/AAAA ou ''",
        "Date d'Accident": "JJ/MM/AAAA",
        "Lieu d'Accident": "Lieu exact (rue, route, etc.)",
        "Délégation": "Délégation géographique correspondant au lieu de l'accident en français",
        "Gouvernorat": "Gouvernorat correspondant au lieu de l'accident en français",
        "Date du PV": "JJ/MM/AAAA",
        "Poste de Police / Garde Nationale": "CHOIX : Poste de Police ou Garde Nationale",
        "Nom du poste": "Nom extrait depuis l'en-tête (ex: Manouba)",
        "Causes de sinistre": "Résumé ultra-concis (ex: Explosion d'une roue)",
        "Total décédés": 0,
        "Total blessés": 0
    }},
    "vehicules": [
        {{
        "id": "vehicule_1",
        "N° Imm": "MAJUSCULES_SANS_ESPACE",
        "Type de véhicule": "CHOIX STRICT LISTE POINT 14",
        "Compagnie": "NOM EN FRANÇAIS (ex: BNA Assurances)",
        "CIN conducteur": "8 chiffres ou null",
        "Nom et Prénom conducteur": "Prénom et Nom du conducteur combinés (alphabet latin) ou null"
        }}
    ],
    "victimes": [
        {{
        "id": "victime_1",
        "Prénom": "Prénom uniquement (alphabet latin)",
        "Nom": "Nom uniquement (alphabet latin)",
        "CIN": "8 chiffres ou null",
        "Age": 0,
        "Date naissance": "JJ/MM/AAAA",
        "Sexe": "Homme ou Femme",
        "Etat social": "CHOIX STRICT : Fonctionnaire Public, Sans emploi ou Profession libérale",
        "Catégorie": "CHOIX STRICT : Conducteur, Piéton ou Passager",
        "Type": "Blessé ou Décédé",
        "vehicule_id": "Lier à l'id du véhicule (ex: vehicule_1) UNIQUEMENT si conducteur, sinon null (si passager/piéton)"
        }}
    ]
}}}}

TEXTE OCR À ANALYSER :
{truncated_text}"""
