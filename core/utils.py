import importlib
import sys
import logging

def sync_and_call(obj, method_name, *args, **kwargs):
    """
    Prüft, ob eine Methode existiert. Falls nicht, wird das Modul 
    neu geladen, um Disk-RAM-Inkonsistenzen zu beheben.
    """
    if hasattr(obj, method_name):
        return getattr(obj, method_name)(*args, **kwargs)
    
    # Falls die Methode fehlt: Versuche das Modul neu zu laden
    try:
        module_name = obj.__class__.__module__
        logging.warning(f"[Safe-Sync] Methode {method_name} nicht gefunden in {module_name}. Erzwinger Reload...")
        
        # Modul aus sys.modules holen und neu laden
        if module_name in sys.modules:
            module = sys.modules[module_name]
            importlib.reload(module)
            
            # Die neue Klassen-Definition abrufen
            new_class = getattr(module, obj.__class__.__name__)
            
            # Die Methode in die laufende Instanz injizieren (Monkey Patching)
            if hasattr(new_class, method_name):
                new_method = getattr(new_class, method_name)
                setattr(obj, method_name, new_method.__get__(obj, obj.__class__))
                logging.info(f"[Safe-Sync] Synchronisation erfolgreich: {method_name} wurde nachgeladen.")
                return getattr(obj, method_name)(*args, **kwargs)
        
        raise AttributeError(f"Methode {method_name} existiert auch nach Reload nicht auf Disk.")
            
    except Exception as e:
        logging.error(f"[Safe-Sync] Kritischer Synchronisationsfehler: {e}")
        raise AttributeError(f"Safe-Sync failed: {str(e)}")
