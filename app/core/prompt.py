PROMPT_TEMPLATE = """\
Vous êtes un expert en analyse de rapports d'accidents tunisiens (PV). 
Vous allez recevoir un texte OCR extrait d'un document PDF. Votre tâche est d'extraire TOUTES les informations structurées directement depuis ce texte.

### MÉTHODOLOGIE DE RÉFLEXION OBLIGATOIRE (CHAIN-OF-THOUGHT) :
Avant d'extraire les valeurs finales, vous devez impérativement utiliser les champs `_reasoning_...` au début du JSON pour :
1. Comprendre la dynamique de l'accident (qui fait quoi).
2. Citer les passages exacts du texte justifiant vos choix pour les causes, les assurances et les véhicules.
3. Filtrer explicitement les victimes (exclure formellement les personnes indemnes) avant de les extraire.

### INSTRUCTIONS D'EXTRACTION :
1. **Date du dépôt du PV** : {date_depot_instruction}
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
4. **Date du PV** : Identifiez la date de clôture ou d'enregistrement administratif du rapport.
Règle de localisation sémantique : Recherchez dans le texte la phrase de formalisation où le "N° du PV" (identifié au point 3) est associé à une date.
Mots-clés pivots : La date recherchée suit généralement des verbes d'enregistrement ou de transmission tels que :
"ضمنت" ou "سجلت" (Enregistré/Inscrit)
"تحت عدد" (Sous le numéro [X]) ... "بتاريخ" (en date du [Y])
"ترويج" (Transmission/Diffusion d'un télégramme/avis lié au numéro)
Logique de validation : Si plusieurs dates sont présentes, la Date du PV est celle qui est syntaxiquement liée au numéro de PV officiel. Elle est obligatoirement égale ou postérieure à la "Date d'Accident".
Format de sortie : YYYY-MM-DD (Convertissez les mois écrits en toutes lettres en chiffres).
5. **Date d'Accident** : Cherchez dans le récit des faits commençant par "جد الحادث jour...". Format YYYY-MM-DD.
5b. **Heure de l'Accident** : Extrayez l'heure la plus proche du lieu ou du récit de l'accident quand elle est explicitement présente. Le format de sortie doit être strictement HH:MM:SS, avec secondes toujours égales à 00 et heures/minutes sur deux chiffres.
6. **Lieu d'Accident / Délégation / Gouvernorat** : 
    - Lisez le contexte de la zone géographique de l'accident (rue, route nationale, point kilométrique, ou la rubrique "مكان الحادث").
    - Extrayez la formulation complète dans le champ "Lieu d'Accident" et traduisez-la TOUJOURS en français (ex: "Route Nationale 1", "Rue Habib Bourguiba"). L'arabe est strictement interdit.
    - À partir de ce lieu, déduisez LOGIQUEMENT la **Délégation** correspondante à cette zone géographique (en français, ex: "Sousse Médina", "La Marsa"...).
    - À partir de ce lieu ou de cette délégation, déduisez également LOGIQUEMENT le **Gouvernorat** dans lequel se trouve l'accident (en français, ex: "Sousse", "Tunis"...).
7. **Causes de sinistre** (CLASSIFICATION MULTIPLE POSSIBLE) :
    - VOTRE MISSION : Vous devez agir comme un classifieur de données. Vous ne devez pas inventer de texte. Votre but est de faire correspondre le récit de l'accident à UNE OU PLUSIEURS VALEURS de la liste officielle ci-dessous.
- LOGIQUE DE DÉCISION (À SUIVRE DANS L'ORDRE) :
    Analyse des faits : Identifiez les "faits générateurs" (les éléments qui ont déclenché l'accident) dans le récit.
    Recherche de correspondance exacte : Parcourez la liste ci-dessous. Si des valeurs correspondent précisément aux infractions citées (ex: l'alcool est mentionné -> "Conduire en état d'ébriété", plus un excès de vitesse -> "Excès de vitesse"), sélectionnez-les TOUTES.
    Priorité sur "عدم اخذ الاحتياطات" : Si le texte arabe cite "عدم اخذ الاحتياطات اللازمة إثناء السياقة" combiné à une autre action spécifique (ex: "و المداهمة من الخلف"), IGNOREZ "Ne pas prendre les précautions nécessaires" et extrayez la ou les causes les plus précises ("Collision par l'arrière").
    # Application des SOLUTIONS DE SECOURS (FALLBACKS) :
    # Si vous identifiez une erreur humaine mais qu'aucun terme de la liste n'est assez précis, ajoutez obligatoirement : "Ne pas prendre les précautions nécessaires".
    # Si vous identifiez un problème sur le véhicule (freins, moteur, direction) sans plus de précision, ajoutez obligatoirement : "Panne mécanique / technique".
    # Si le texte est totalement muet sur la cause ou contradictoire, utilisez obligatoirement : "Non mentionné / Non déterminé".
- RÈGLES CRUCIALES :
    INTERDICTION ABSOLUE de créer une nouvelle catégorie ou de modifier l'orthographe de la liste.
    COPIER-COLLER EXACT : Les valeurs dans le JSON doivent être identiques caractère par caractère à la liste ci-dessous et formatées en tant que liste (array) de chaînes de caractères.
- LISTE OFFICIELLE OBLIGATOIRE :
    Marcher sur la chaussé, Stationnement innaproprié, Dépassement interdit, Excès de vitesse, Non respect de la priorité, Téléphone portable au volant, Ne pas prendre les précautions nécessaires, Non respect des signalisations de l'agent de Police de la circulation, Non respect de la distance de sécurité, Non respect des signalisations, Non respect du panneau "céder le passage", Sortie (soudaine) de la route/chaussée /pavé, Non mentionné / Non déterminé, Panneau "Attention Travaux" non affiché, Ne pas signaler "véhicule en panne", Nouveau en conduite, Panne technique, Ne pas prendre les précautions nécessaires lors du dépassement au rond point "céder le passage", Véhicule non destiné pour le transport des marchandises, Non respect des feux de signalisations, Interdiction de circuler des poids lourds, Conduite sans assurance + sans permis de conduire, Acte de violence, Chute du / des piéton(s), Panne mécanique / technique, Arrêt innaproprié, Défaut d'attention, accidents en chaine, Changer de direction, Collision par l'arrière, Chutes sur la route, Passage à niveau, Rouler dans un sens interdit, Vitesse réduite, Circulation sur trottoir, Circulation sur passage piétons, Infraction routière, Conduire en état d'ébriété, Conduire en état de fatigue, Rouler sans lumière la nuit, Fraude, Explosion d'une roue, Route glissante.

8. **nationalGuardHQ / policeHQ** : Identifiez le nom géographique principal (la ville ou région) en analysant les en-têtes administratifs situés en haut à droite de chaque page. Ce nom se trouve généralement à la fin d'une ligne hiérarchique, souvent précédé de la particule "ب" (en/à).
Exemples de structures à repérer :
"... لحوادث المرور بمنوبة" → extraire "Manouba".
"منطقة الحرس الوطني بقابس" → extraire "Gabès".
Comme ces en-têtes se répètent sur toutes les pages, utilisez la page la plus nette pour confirmer. Si `_reasoning_Poste_Type` est "Garde Nationale", inscrivez ce nom dans le champ `nationalGuardHQ` et mettez la valeur `null` dans `policeHQ`. Inversement si le type est un "Poste de Police".
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
10b. **Numéro de CIN** : Cherchez systématiquement la Carte d'Identité Nationale (ex: "بطاقة تعريف", "ب.ت.و") pour CHAQUE victime. Si vous trouvez un N° de CIN (généralement 8 chiffres), affectez-le au champ "CIN". Si introuvable, indiquez impérativement `null`.
11. **Âge et Date de Naissance des victimes (RÈGLE OBLIGATOIRE)** : 
    - **PRIORITÉ 1 (LA PLUS IMPORTANTE)** : Recherchez SYSTÉMATIQUEMENT et EN PREMIER la date de naissance dans le document en utilisant les mots-clés arabes suivants :
        * "مولود في" (né le)
        * "مولود بتاريخ" (né à la date)
        * "تاريخ الولادة" (date de naissance)
        * "ولد في" (né en)
    - Si vous trouvez une date de naissance, extrayez-la au format YYYY-MM-DD et mettez-la dans le champ "birthDate".
    - **PRIORITÉ 2 (SEULEMENT SI DATE DE NAISSANCE NON TROUVÉE)** : Si la date de naissance n'est PAS disponible, mais que l'âge est écrit EXPLICITEMENT dans le PV (ex: "34 ans", "عمره 34 سنة"), ignorez l'âge car l'API attend uniquement des dates de naissance.
    - Ne tentez PAS de calculer l'âge vous-même. Extrayez uniquement les informations présentes dans le document.
12. **Séparation des Noms et Prénoms** : Procédez à l'extraction sélective des noms et prénoms. Vous devez extraire le prénom complet dans le champ 'Prénom' et le nom de famille dans le champ 'Nom'.
RÈGLE CRUCIALE POUR LES PRÉNOMS COMPOSÉS : En arabe, de nombreux prénoms sont composés (ex: "محمد علي", "محمد أمين", "فاطمة الزهراء", "سيف الدين"). **Ne séparez jamais un prénom composé !** Le deuxième mot (ex: "علي" ou "أمين") appartient au prénom et ne doit SURTOUT PAS être extrait comme nom de famille. 
Règle d'exclusion : Ignorez systématiquement les noms intermédiaires (le nom du père) et la particule de filiation "بن" ou "bin".
Format de sortie : Effectuez une transcription phonétique impérativement en français (alphabet latin). L'usage de caractères arabes dans le JSON final est strictement interdit.
Exemples : 
- "محمد بن شادلي منصوري" → Prénom: Mohamed, Nom: Mansouri.
- "محمد علي الطرابلسي" → Prénom: Mohamed Ali, Nom: Trabelsi.
- "سيف الدين بن محمود" → Prénom: Seifeddine, Nom: Mahmoud.
13. **Catégorisation de l'État Social/Profession (MAPPING)** : 
    - **Fonctionnaire Public** : État/Secteur public (Enseignant, Professeur, Policier, Militaire).
    - **Sans emploi** : Chômeur, Femme au foyer, Étudiant, Élève, Retraité, Enfant.
    - **Profession libérale** : Secteur privé, Ouvrier, Journalier, Commerçant, Agriculteur, Chauffeur.

14. **Type de véhicule (MAPPING HIÉRARCHIQUE ET STRICT)**:
    Consigne : Pour chaque véhicule identifié, vous devez mapper sa nature vers UNE SEULE valeur de la liste officielle ci-dessous. Utilisez les indices textuels du procès-verbal pour choisir la catégorie la plus précise.

    *) Liste Officielle (Valeurs Autorisées) :
    ['Louage', 'Taxi Individuel', 'Véhicule rapide d’intervention', 'Motocyclette légère (50-125 cm³)', 'Vélo ordinaire', 'Train', 'Engin de travaux', 'Tricycle à moteur', 'Motocyclette (supérieur à 125cm3)', 'Quadricycles à moteur', 'Taxi collectif', 'Véhicule administratif', 'Auto Ecole', 'Location', 'Véhicule de transport rural', 'Véhicule touristique privé (transport personnel)', 'Taxi Touristique', 'Trottinette', 'Autobus public (transport régional) - transport personnel', 'Motocyclette (supérieur à 50cm3) - Administratif', 'Autobus TCV (transport en commun de voyageurs)', 'Ambulance', 'Objets impliqués', 'Bus', 'Motocyclette (inférieur à 50cm3)', 'voiture', 'Métro', 'véhicules Electrique', 'Remorquage', 'Remorque et semi remorque', 'Tracteur', 'véhicules', 'Camion']

    

    **) Guide de Décision et Mots-Clés :

    Véhicules de Tourisme :

    'voiture' : Terme générique ("voiture particulière", "M1") sans précision d'usage.  

    'Véhicule touristique privé (transport personnel)' : Si mention de "propriété privée" ou "usage personnel".  

    'Location' : Si mention d'une agence de location ou "voiture louée".  

    'Véhicule administratif' : Si mention de "ministère", "société publique" ou présence d'une plaque rouge/bleue.  

    Transport Public & Collectif :

    'Louage' : Mention explicite de "Louage" ou transport interurbain entre villes.  

    'Taxi Individuel' : Mention de "Taxi" sans autre précision.  

    'Véhicule de transport rural' : Transport de passagers en zone rurale (souvent mentionné comme "Transport Rural").  

    'Autobus public (transport régional) - transport personnel' : Mention de "Bus SRT", "Bus régional" ou grand autocar de transport public.  

    Deux-roues et assimilés :

    'Motocyclette (inférieur à 50cm3)' : Si mention de "Vélomoteur", "Mob" ou petite cylindrée.  

    'Motocyclette légère (50-125 cm³)' : Si mention de "Scooter" ou cylindrée moyenne.  

    'Motocyclette (supérieur à 125cm3)' : Si mention de "Grosse cylindrée" ou "Moto de sport".  

    Poids lourds et Travaux :

    'Camion' : Mention de "Poids lourd" ou transport de marchandises.  

    'Tracteur' : Si mention explicite de "Tracteur agricole".  

    'Engin de travaux' : Pelleteuse, bulldozer ou matériel de chantier.  

    Urgence et Spéciaux :

    'Ambulance' : Véhicule de secours médical.  

    'Objets impliqués' : Si le dommage concerne un obstacle fixe (mur, poteau, arbre) et non un autre véhicule.  

    ++ Deux-roues (RÈGLE DE PRIORITÉ) :

        'Motocyclette (inférieur à 50cm3)' (VALEUR PAR DÉFAUT) : Utilisez cette catégorie pour tout deux-roues motorisé (vélomoteur, mobylette, scooter) s'il n'y a aucune précision sur la cylindrée dans le texte.  

        Exceptions (SI INDICE PRÉCIS) :

        Utilisez 'Motocyclette légère (50-125 cm³)' UNIQUEMENT si le texte mentionne explicitement un indice de capacité (ex: "100cc", "125cc") ou un modèle de scooter de taille moyenne (ex: "Vespa", "Piaggio Liberty").  

        Utilisez 'Motocyclette (supérieur à 125cm3)' UNIQUEMENT si le texte mentionne une "Grosse cylindrée" ou une marque de moto puissante (ex: "Kawasaki", "BMW", "Yamaha T-Max").

    ***) RÈGLE D'OR :
    La valeur extraite doit correspondre EXACTEMENT à l'orthographe de la liste officielle. Si le texte est vague, privilégiez la catégorie la plus simple ('voiture' pour les automobiles, 'véhicules' pour les types indéterminés).
    
15. **Type de Poste (_reasoning_Poste_Type)** : Identifiez l'organisme ayant rédigé le PV en analysant l'en-tête (en haut à droite). Vous devez effectuer un choix binaire obligatoire pour le champ interne `_reasoning_Poste_Type` :
    - Si vous voyez les mots "الحرس الوطني", inscrivez exclusivement : "Garde Nationale". Vous devez utiliser cette valeur pour remplir `nationalGuardHQ` et mettre `policeHQ` à `null`.
    - Si vous voyez les mots "الأمن الوطني" ou "الشرطة", inscrivez exclusivement : "Poste de Police". Vous devez utiliser cette valeur pour remplir `policeHQ` et mettre `nationalGuardHQ` à `null`.
    Interdiction : Ne créez aucune autre catégorie.

### LOGIQUE PRÉCISE POUR LES VÉHICULES :
16. **Identification du Véhicule ("N° Imm") - Immatriculation ou Châssis :**
    - STRATÉGIE DE RECHERCHE : Identifiez en priorité le numéro d'immatriculation (plaque minéralogique). Si celui-ci est absent ou illisible, extrayez impérativement le numéro de série ou de châssis (souvent plus long et complexe).
    - NETTOYAGE STRICT DU FORMAT : Toute valeur extraite doit être normalisée : supprimez tous les espaces blancs, étoiles ou caractères spéciaux qui ne font pas partie du code (ex: "ABC - 123 * 45" -> "ABC12345").
    - EXTRACTION PRIORITAIRE DES CODES LONGS (CHÂSSIS/VIN) : Une attention particulière doit être portée aux identifiants longs (ex: 17 caractères). Ne tronquez jamais ces numéros. Toute chaîne alphanumérique longue identifiée comme un châssis doit être extraite dans son intégralité (ex: "1FA6P8CF4G52XXXXX").
    - CONSERVATION DES MARQUEURS NATIONAUX ET INTERDICTION DE "TUN" : Si un pays ou une mention spécifique est écrit entre les chiffres (ex: TU, TN, F, تونس), remplacez-le par son code international ("TU" pour la Tunisie) sans espaces. L'utilisation de "TUN" est STRICTEMENT INTERDITE. Si vous vous apprêtez à écrire "123TUN456", vous devez immédiatement le corriger en "123TU456".
    - ABSENCE DE MARQUEUR : Si la plaque utilise uniquement des tirets ou des points sans mention de pays (ex: "11-222-333"), conservez la ponctuation d'origine telle quelle sans rien inventer (ex: "11-222-333").
    - CONVERSION DES RÉGIMES SPÉCIAUX : Détectez les mentions de régimes particuliers (ex: "Régime Suspensif", "ن ت") et convertissez-les en préfixes standards (ex: "1234 ن ت" -> "RS1234").
    - FORMATS D'IMMATRICULATION ATYPIQUES : Si le numéro ne correspond à aucun format classique abordé ci-dessus, repérez et extrayez n'importe quel autre format aléatoire ou atypique (mélange de lettres, chiffres, etc.) à condition que le contexte du texte le désigne explicitement comme étant la plaque ou l'immatriculation du véhicule.
    - RÈGLE DE SORTIE : Le champ "registrationNumber" doit contenir soit la plaque, soit le châssis.
    - ZÉRO HALLUCINATION : Si aucune donnée d'identification n'est présente dans le texte, renvoyez null.
    - RÈGLE CRITIQUE — DEUX-ROUES ET VÉHICULES MOTORISÉS (MOTOS, SCOOTERS, TRICYCLES) :
        ⚠️ L'ABSENCE D'ASSURANCE N'IMPLIQUE PAS L'ABSENCE DE PLAQUE. Ce sont deux informations INDÉPENDANTES.
        Une moto, un scooter ou un tricycle PEUT être "Non assuré" ET avoir quand même une plaque d'immatriculation (ex: "123TU4567", "12-345-678").
        OBLIGATION : Même si le véhicule est de type deux-roues OU s'il est explicitement mentionné comme "غير مؤمنة" (non assuré), vous devez TOUJOURS chercher et extraire son numéro d'immatriculation ou de châssis s'il est présent dans le texte.
        Exceptions légitimes où `null` est acceptable pour `registrationNumber` :
            * Vélo ordinaire (bicyclette sans moteur) : non immatriculé.
            * Trottinette non motorisée : non immatriculée.
            * Le texte ne mentionne explicitement aucun numéro de plaque ni de châssis pour ce véhicule.
        Pour tout autre véhicule motorisé (moto, scooter, tricycle à moteur, quadricycle) : cherchez activement la plaque avant de retourner null.

16b. **Modèle du Véhicule (model)** : 
    - STRATÉGIE DE RECHERCHE : Cherchez dans la section descriptive du véhicule le nom du modèle exact. Les mots-clés pivots incluent :
        * En arabe : "نموذج" (modèle), "طراز" (type/modèle), "صنف" (classe), souvent suivis du nom en arabe ou translittéré.
        * En français : "Modèle", "Type", "Marque et modèle" ou simplement le nom commercial du modèle (ex: "Clio", "Golf", "Civic").
    - TRANSCRIPTION OBLIGATOIRE EN FRANÇAIS : Si le modèle est écrit en arabe (ex: "هيونداي أكسنت"), procédez à une translittération phonétique en français (ex: "Accent"). Vous devez TOUJOURS écrire le modèle en alphabet latin, jamais en arabe.
    - STRUCTURE ALPHANUMÉRIQUE : Le modèle peut être composé de lettres et/ou de chiffres représentant la désignation commerciale exacte du modèle (ex: "Golf 7", "Clio IV", "C-HR", "M340i", "A3 35 TFSI").
    - ABSENCE OU INCERTITUDE : Si le modèle ne peut pas être trouvé, reste flou ou ambigü dans le document, renvoyez null.

16c. **Fabricant/Marque du Véhicule (manufacturer)** :
    - STRATÉGIE DE RECHERCHE : Identifiez le fabricant du véhicule en cherchant :
        * En arabe : "الصانع" (fabricant), "الماركة" (la marque), "مصنع" (usine/fabricant), ou simplement le nom de la marque directement mentionné (ex: "تويوتا", "فولكسفاغن", "بيجو").
        * En français : "Marque", "Fabricant", "Constructeur" ou le nom de la marque automobile connue (ex: "Toyota", "Volkswagen", "Peugeot").
    - FORMAT OBLIGATOIRE EN MAJUSCULES : Le fabricant doit TOUJOURS être écrit en MAJUSCULES (ex: "TOYOTA", "PEUGEOT", "MERCEDES-BENZ", "VOLKSWAGEN").
    - TRANSCRIPTION OBLIGATOIRE EN FRANÇAIS : Si la marque est écrite en arabe, procédez à une translittération phonétique en français/anglais standard (ex: "سوزوكي" → "SUZUKI", "هيونداي" → "HYUNDAI").
    - FORMAT STANDARD INTERNATIONAL : Utilisez les noms de marques tels qu'ils sont reconnus internationalement et dans les listes officielles (ex: "FORD" et non "FORTES", "PEUGEOT" et non "POUGEOT").
    - ABSENCE OU INCERTITUDE : Si le fabricant ne peut pas être trouvé, reste flou ou ambigü, renvoyez null.

That confirms it — instruction 17 is a single thin line with zero guidance on where to find the CIN, how to link it to the right vehicle, or what to do when the driver isn't a victim. Here are the exact changes:

Change 1 — Expand instruction 17 (the only change needed in the instructions block)
Location: Line 157 — replace this single line:
17. **Conducteurs des véhicules** : Pour chaque véhicule impliqué, identifiez le conducteur. Extrayez uniquement son numéro de CIN dans le champ "driverIdentity".
Replace with:
17. **Conducteurs des véhicules (driverIdentity)** : Pour chaque véhicule impliqué, identifiez le conducteur et extrayez uniquement son numéro de CIN (8 chiffres) dans le champ `driverIdentity`.
    - STRATÉGIE DE RECHERCHE : Le CIN du conducteur se trouve dans la section descriptive du véhicule, souvent introduit par les mots-clés arabes :
        * "بطاقة تعريف" / "ب.ت.و" / "رقم البطاقة" (numéro de carte d'identité)
        * "يقودها" / "سائقها" / "بقيادة" (conduit par)
        Le CIN est généralement un nombre de 8 chiffres placé après l'identité du conducteur.
    - LINKAGE VÉHICULE↔CONDUCTEUR : Associez le CIN au bon véhicule en vous basant sur le contexte narratif (ex: "السيارة الأولى ... يقودها ... ب.ت.و 12345678" → ce CIN appartient au conducteur du premier véhicule).
    - CAS DU CONDUCTEUR VICTIME : Si le conducteur figure également dans la liste des victimes, dupliquez son CIN dans les deux endroits : `driverIdentity` dans `vehicles[]` ET `identityNumber` dans `victims[]`. Ce sont deux champs indépendants.
    - CAS DU CONDUCTEUR NON VICTIME (INDEMNE) : Si le conducteur est indemne (non listé dans les victimes), son CIN doit quand même apparaître dans `driverIdentity`. Ne le laissez pas à null sous prétexte qu'il n'est pas blessé.
    - ABSENCE : Si aucun CIN n'est trouvable pour le conducteur d'un véhicule, renvoyez null.
18. **Établissement de santé (Hôpital/Clinique)** : Identifiez le lieu de soins (mots-clés "مستشفى", "مصحة", "معهد" associés à "تم نقله" ou "توجيهه").
    - Transcrivez impérativement en français (ex: "Hôpital Charles Nicolle", "Clinique Hannibal").
    - ATTENTION AUX TRANSFERTS (CAS MULTIPLES) : Suivez le parcours médical détaillé dans le texte. Si au cours du récit de l'accident, la victime a été admise dans plusieurs établissements successivement (ex: d'abord un hôpital local pour les premiers soins, puis un transfert vers un établissement de référence pour une opération), vous DEVEZ déduire et retenir EXCLUSIVEMENT l'établissement final et définitif vers lequel la victime a été orientée en fin de compte. Rentrez ce nom sous forme de chaîne de caractères simple (pas de liste).
    - Si aucune mention n'est trouvée pour la victime, attribuez la valeur null.

19. **Catégorisation de l'État Social (MAPPING STRICT)** :
    - Fonctionnaire Public : Secteur public, administration, police, militaires, enseignement (primaire/secondaire).
    - Enseignant universitaire : Uniquement pour l'enseignement supérieur.
    - Profession libérale : TOUT le secteur privé (Ouvriers, commerçants, ingénieurs, avocats, chauffeurs, journaliers).
    - Sans emploi : Chômeurs, femmes au foyer, étudiants, élèves, enfants.
    - Retraité : Toute personne retraitée (متقاعد).
    - Agent d'exécution : Personnel technique ou d'exécution spécifique.
    - Médecin expert : Choisir la valeur la plus précise : "Médecin expert - laboratoire", "Médecin expert judiciaire", "Médecin expert assurance" ou par défaut "Médecin expert".
    - Sports : "Pétanqueur professionnel" ou "Pétanqueur" (si mentionné explicitement).
    
    - RÈGLE : La valeur extraite doit correspondre EXACTEMENT à l'une des entrées de PROFESSION_LIST = ['Retraité', 'Sans emploi', 'Profession libérale', "Agent d'exécution", 'Enseignant universitaire', 'Pétanqueur professionnel', 'Pétanqueur', 'Médecin expert - laboratoire', 'Médecin expert', 'Médecin expert judiciaire', 'Médecin expert assurance', 'Fonctionnaire Public'].

20. 15. **Informations Entreprise (Victimes)** :
    - Examinez si la victime est mentionnée comme agissant pour le compte d'une société ou si un identifiant fiscal (Matricule Fiscal) est associé à son identité.
    - **belongCompany** : `true` si le texte mentionne une entreprise employeuse ou un matricule fiscal pour la victime, sinon `false`.
    - **companyFiscalTaxId** : Extrayez le matricule fiscal (souvent composé de chiffres et de lettres, ex: 1234567/A/M/000). Si `belongCompany` est `false`, ce champ doit être `null`.

21. 17. **Gouvernorat du décès (MAPPING STRICT)** :
    - Si la victime est décédée, identifiez le gouvernorat où le décès a été constaté.
    - Vous devez impérativement mapper ce lieu vers l'une des valeurs suivantes (en MAJUSCULES) :
    'ARIANA', 'BEJA', 'GABES', 'GAFSA', 'JENDOUBA', 'KAIROUAN', 'KASSERINE', 'KEBILI', 'KEF', 'MAHDIA', 'MANOUBA', 'MEDENINE', 'MONASTIR', 'NABEUL', 'SFAX', 'SOUSSE', 'TATAOUINE', 'TOZEUR', 'TUNIS', 'ZAGHOUAN', 'BIZERTE', 'SILIANA', 'BEN_AROUS', 'SIDI_BOUZID'.
    - Si le lieu n'est pas clair, utilisez le gouvernorat de l'accident ou `null`.

22. **Cause médicale du décès (MAPPING STRICT)** :
    - Analysez les mentions relatives au décès de la victime pour choisir l'une des trois options suivantes :
    - "Suite à l’accident" : Si le texte indique que la mort est survenue sur le coup, lors du transport, ou à l'hôpital à cause des blessures subies.
    - "Non déterminé" : Si le PV mentionne que la cause exacte sera définie par une autopsie ultérieure ou si le texte est ambigu sur le lien direct.
    - "Autre" : Si le décès est dû à une cause médicale préexistante (ex: malaise cardiaque avant l'impact) ou sans lien direct avec le choc.


### RÈGLES DE FORMATAGE :
- Langue : FRANÇAIS exclusivement.
- Causes de sinistre : Fournissez une LISTE de chaînes de caractères (ex: ["Excès de vitesse", "Collision par l'arrière"]).
- Compagnie : Nom commercial en MAJUSCULES. **Si le texte mentionne "AMI" ou "أمي", écrivez "BNA Assurance"**. Si "غير مؤمنة" -> "Non assuré".
- N° Imm : MAJUSCULES_SANS_ESPACE. Suivez scrupuleusement les règles du point 16 (Interdiction d'inventer le TU).
- Type de véhicule : **CHOIX STRICT** dans la liste définie au point n°14. Ne créez aucune autre catégorie.
- Profession : CHOIX STRICT : 'Retraité', 'Sans emploi', 'Profession libérale', "Agent d'exécution", 'Enseignant universitaire', 'Pétanqueur professionnel', 'Pétanqueur', 'Médecin expert - laboratoire', 'Médecin expert', 'Médecin expert judiciaire', 'Médecin expert assurance', 'Fonctionnaire Public'
- Victimes : Sexe ("MALE"/"FEMALE"), Type ("INJURY"/"DEATH"), Catégorie ("DRIVER"/"PASSENGER"/"PEDESTRIAN").
- Dates : Utilisez strictement le format YYYY-MM-DD.

### STRUCTURE JSON ATTENDUE :
{{
    "requestId": "{requestId}",
    "_reasoning_contexte": "1. Résumez la dynamique de l'accident : qui conduisait quoi, dans quelle direction, et que s'est-il passé ?",
    "_reasoning_lieu": "2. Citez le passage décrivant le lieu exact du sinistre (rue, route, point kilométrique, etc.) et déduisez-en son emplacement.",
    "_reasoning_causes": "3. Citez le passage précis traitant de l'infraction/panne, puis déduisez-en formellement le terme STRICT dans la liste officielle.",
    "_reasoning_vehicules": "4. Listez les véhicules impliqués. Pour chaque assurance trouvée, appliquez le mapping autorisé (ex: 'AMI' devient 'BNA Assurances'). Identifiez également le modèle et la marque du véhicule. IMPORTANT : Pour chaque deux-roues ou véhicule non assuré, vérifiez EXPLICITEMENT si une plaque ou un numéro de châssis est mentionné dans le texte avant de mettre null dans registrationNumber.",
    "_reasoning_victimes": "5. Cherchez la rubrique des dégâts corporels. Comptez blessés/morts. Identifiez âge. S'il y a des blessés, analysez leur parcours de soin et déterminez expressément l'établissement final dans lequel la victime a été admise (l'hôpital ultime). EXCLUEZ les personnes indemnes.",
    "_reasoning_Poste_Type": "6. CHOIX : Poste de Police ou Garde Nationale",
    "_reasoning_Total_decedes": "7. Total décédés (nombre entier)",
    "_reasoning_Total_blesses": "8. Total blessés (nombre entier)",
    

    "reportNumber": "Valeur numérique (ex: 21.5.09)",
    "accidentDate": "YYYY-MM-DD ou null",
    "accidentTime": "HH:MM:SS ou null",
    "accidentAddress": "Lieu exact (rue, route, etc.)",
    "governorate": "Gouvernorat correspondant au lieu de l'accident en français",
    "region": "Délégation géographique correspondant au lieu de l'accident en français",
    "nationalGuardHQ": "Nom du poste si Garde Nationale, sinon null",
    "policeHQ": "Nom du poste si Poste de Police, sinon null",
    "claimReasons": ["Exemple cause 1", "Exemple cause 2"],
    "submissionDate": "YYYY-MM-DD ou null",
    "reportDate": "YYYY-MM-DD ou null",
    "vehicles": [
        {{
        "type": "VALEUR EXACTE DE LA LISTE (ex: Louage, Taxi Individuel, etc.)",
        "insurance": "NOM EN FRANÇAIS (ex: BNA Assurances). IMPORTANT: Si le véhicule n'a pas d'assurance (ex: bicyclette, charrette) ou s'il est explicitement mentionné comme non assuré, écrivez 'Non assuré'. Ne mettez JAMAIS null pour un défaut d'assurance",
        "model": "Modèle du véhicule ou null",
        "manufacturer": "Marque du véhicule ou null",
        "registrationNumber": "MAJUSCULES_SANS_ESPACE ou null",
        "driverIdentity": "8 chiffres ou null"
        }}
    ],
    "victims": [
        {{
        "identityNumber": "8 chiffres ou null",
        "firstName": "Prénom uniquement (alphabet latin)",
        "lastName": "Nom uniquement (alphabet latin)",
        "gender": "MALE ou FEMALE",
        "birthDate": "YYYY-MM-DD ou null",
        "address": "Adresse de la victime ou null",
        "casualtyType": "DEATH ou INJURY",
        "casualtyCategory": "DRIVER, PASSENGER ou PEDESTRIAN",
        "deathDate": "YYYY-MM-DD ou null si vivant",
        "deathTime": "HH:MM:SS ou null",
        "deathPlace": "Lieu du décès ou null",
        "deathGovernorate": "Gouvernorat du décès: VALEUR STRICTE (ex: TUNIS, SFAX, BEN_AROUS) ou null"
        "deathMedicalCause": "CHOIX STRICTE: 'Suite à l’accident', 'Non déterminé' ou 'Autre'",
        "healthInstitution": "Nom du dernier Hôpital/Clinique fréquenté ou null",
        "profession": "VALEUR EXACTE (ex: Profession libérale, Fonctionnaire Public, etc.)",    
        "belongCompany": "boolean (true/false)",
        "companyFiscalTaxId": "Matricule fiscal ou null"    
        }}
    ]
}}

TEXTE OCR À ANALYSER :
{truncated_text}
"""