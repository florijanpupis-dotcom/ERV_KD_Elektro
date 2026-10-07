import requests

# ⚠️ ZAMIJENITE OVO S VAŠIM PRAVIM PROJECT ID-jem IZ KORAKA 1
PROJECT_ID = "ERV-KD-Elektro"  
BASE_URL = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents"

class FirestoreDB:
    @staticmethod
    def get_collection(collection_name: str) -> list:
        """Dohvaća sve dokumente iz zadane kolekcije u obliku liste rječnika (dict)."""
        try:
            res = requests.get(f"{BASE_URL}/{collection_name}")
            if res.status_code == 200:
                data = res.json()
                documents = []
                for doc in data.get("documents", []):
                    doc_id = doc["name"].split("/")[-1]
                    fields = doc.get("fields", {})
                    
                    # Pretvaranje Firestore REST formata u običan Python dict
                    parsed = {}
                    for key, val in fields.items():
                        parsed[key] = list(val.values())[0]
                    parsed["id"] = doc_id
                    documents.append(parsed)
                return documents
            return []
        except Exception as e:
            print(f"Greška pri dohvaćanju s Firestorea: {e}")
            return []

    @staticmethod
    def add_document(collection_name: str, doc_id: str, data_dict: dict) -> bool:
        """Sprema ili ažurira dokument u Firestore bazi."""
        try:
            firestore_fields = {}
            for k, v in data_dict.items():
                if isinstance(v, (int, float)):
                    firestore_fields[k] = {"doubleValue": float(v)}
                else:
                    firestore_fields[k] = {"stringValue": str(v)}

            payload = {"fields": firestore_fields}
            url = f"{BASE_URL}/{collection_name}?documentId={doc_id}"
            
            res = requests.post(url, json=payload)
            return res.status_code == 200
        except Exception as e:
            print(f"Greška pri spremanju na Firestore: {e}")
            return False