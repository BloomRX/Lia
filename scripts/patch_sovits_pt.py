# -*- coding: utf-8 -*-
# ============================================================================
#  patch_sovits_pt.py
#  Adiciona suporte a PORTUGUÊS (pt-BR) no GPT-SoVITS v2/v2Pro, SEM ampliar o
#  vocabulário nem retreinar o modelo base:
#
#     1. Instala GPT_SoVITS/text/portuguese.py  (G2P grafema->fonema pt-BR)
#        que emite fonemas JÁ EXISTENTES em symbols2.symbols (set ARPABET).
#     2. cleaner.py       -> adiciona "pt": "portuguese" no language_module_map.
#     3. TTS.py           -> adiciona "pt" em v1/v2_languages.
#     4. TextPreprocessor -> trata "pt" como idioma explícito (não passa pelo
#                            LangSegmenter, que reclassificaria como 'en').
#     5. 1-get-text.py    -> aceita "PT"/"pt" no mapa de idioma do treino.
#
#  Idempotência por SENTINELA (linha única) para poder rodar várias vezes.
#
#  Uso:
#    python patch_sovits_pt.py <GPT-SoVITS_root>   (ex.: J:\Lia\GPT_SoVITS)
# ============================================================================
import sys
import re
import os
import shutil
import base64

SENT_PT = "# LIA_FIX_PT_SUPPORT"

# O módulo G2P (portuguese.py) embutido em base64 para evitar problemas de
# escape. Escrito em GPT_SoVITS/text/portuguese.py no runtime.
PORTUGUESE_B64 = "IyAtKi0gY29kaW5nOiB1dGYtOCAtKi0KIiIiCnBvcnR1Z3Vlc2UucHkg4oCUIEcyUCAoZ3JhZmVtYS0+Zm9uZW1hKSBwYXJhIHBvcnR1Z3XDqnMgYnJhc2lsZWlybyAocHQtQlIpLgoKR2VyYSBzZXF1w6puY2lhcyBkZSBmb25lbWFzIHF1ZSBKw4EgRkFaRU0gUEFSVEUgZG8gdm9jYWJ1bMOhcmlvIGRvIEdQVC1Tb1ZJVFMgdjIKKHN5bWJvbHMyLnN5bWJvbHMpLCByZXV0aWxpemFuZG8gb3Mgc8OtbWJvbG9zIEFSUEFCRVQgZXhpc3RlbnRlcy4gQXNzaW0gbsOjbyDDqQpwcmVjaXNvIGFtcGxpYXIgbyB2b2NhYnVsw6FyaW8gbmVtIHJldHJlaW5hciBvIG1vZGVsbyBiYXNlOiBjYWRhIHPDrW1ib2xvIGRlCnNhw61kYSBqw6EgZXhpc3RlIGVtIHN5bWJvbHMyLnN5bWJvbHMuCgpDYXJhY3RlcsOtc3RpY2FzIGNvbnNpZGVyYWRhcyAocHQtQlIgcGFkcsOjbyk6CiAgLSBSZWR1w6fDo28gZGUgdm9nYWlzIMOhdG9uYXMgZmluYWlzIChlLT5JWSwgby0+VVcpIGUgInMiLyJ6IiBmaW5haXMgc3VyZG9zLgogIC0gRGl0b25nb3Mgb3JhaXM6IGFpLCBhdSwgZWksIGV1LCBvaSwgb3UsIHVpLCBpdS4KICAtIFZvZ2FpcyBuYXNhaXMgKGF+LCBvfiwgZX4sIGl+LCB1fikgLT4gViArIE4uCiAgLSBEaWdyYWZvcyBjaC0+U0gsIG5oLT5OLCBsaC0+TCwgcnItPkhILCBzcy0+UywgZ3UvcXUuCiAgLSAibCIgZW0gZmluYWwgZGUgc8OtbGFiYSAtPiBXICh2b2NhbGl6YcOnw6NvKS4KICAtIFRvbmljaWRhZGUgZXN0aW1hZGEgcG9yIHJlZ3JhcyBvcnRvZ3LDoWZpY2FzIC0+IGTDrWdpdG8gMS8wIG5vIHPDrW1ib2xvIGRhCiAgICB2b2dhbC4KClF1YWxxdWVyIHPDrW1ib2xvIGZvcmEgZGUgc3ltYm9sczIuc3ltYm9scyDDqSB0cm9jYWRvIHBvciAiVU5LIi4KIiIiCgppbXBvcnQgcmUKCiMgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tCiMgVm9nYWwgc2ltcGxlcyAoMSBsZXRyYSkgLT4gYmFzZSBBUlBBQkVUIChzZW0gZMOtZ2l0byBkZSBhY2VudG8pLgojIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLQpfU0lOR0xFID0gewogICAgImEiOiAiQUEiLCAiw6EiOiAiQUEiLCAiw6AiOiAiQUEiLCAiw6IiOiAiQUEiLCAiw6MiOiAiQUEiLCAiw6QiOiAiQUEiLAogICAgImUiOiAiRVkiLCAiw6kiOiAiRUgiLCAiw6giOiAiRUgiLCAiw6oiOiAiRVkiLCAi4bq9IjogIkVIIiwgIsOrIjogIkVZIiwKICAgICJpIjogIklZIiwgIsOtIjogIklZIiwgIsOuIjogIklZIiwgIsOsIjogIklZIiwgIsSpIjogIklZIiwgIsOvIjogIklZIiwKICAgICJvIjogIk9XIiwgIsOzIjogIkFPIiwgIsOyIjogIkFPIiwgIsO0IjogIk9XIiwgIsO1IjogIk9XIiwgIsO2IjogIk9XIiwKICAgICJ1IjogIlVXIiwgIsO6IjogIlVXIiwgIsO7IjogIlVXIiwgIsO5IjogIlVXIiwgIsWpIjogIlVXIiwgIsO8IjogIlVXIiwKICAgICJ5IjogIklZIiwgIsO9IjogIklZIiwKfQoKIyBEaXRvbmdvczogcGFyIGRlIHZvZ2FpcyAobm9ybWFsaXphZGFzIHNlbSBhY2VudG8sIG1pbsO6c2N1bGFzKSAtPiBiYXNlIEFSUEFCRVQuCl9ESVBIVEhPTkcgPSB7CiAgICAiYWkiOiAiQVkiLCAiYXUiOiAiQVciLCAiZWkiOiAiRVkiLCAiZXUiOiAiRVkiLCAib2kiOiAiT1kiLAogICAgIm91IjogIk9XIiwgInVpIjogIlVXIiwgIml1IjogIlVXIiwgInVlIjogIlVXIiwgIm9vIjogIk9XIiwKICAgICMgZGl0b25nb3MgbmFzYWlzIChhfm8sIGF+ZSwgb35lKSAtPiBkaXRvbmdvIG9yYWwgKyBOCiAgICAiYW8iOiAiQVciLCAiYWUiOiAiQVkiLCAib2UiOiAiT1kiLAp9CgojIExldHJhcyBkZSB2b2dhbCAoYmFzZSwgc2VtIGFjZW50bykgcGFyYSBub3JtYWxpemFyIGNvbXBhcmHDp8O1ZXMuCl9WT1dFTF9DSEFSUyA9IHNldCgiYWVpb3V5w6HDoMOiw6PDpMOpw6jDquG6vcOrw63DrMOuxKnDr8Ozw7LDtMO1w7bDusO5w7vFqcO8w70iKQoKZGVmIF9zdHJpcF9tYXJrcyhjaCk6CiAgICB0YWJsZSA9IHsiw6EiOiAiYSIsICLDoCI6ICJhIiwgIsOiIjogImEiLCAiw6MiOiAiYSIsICLDpCI6ICJhIiwKICAgICAgICAgICAgICLDqSI6ICJlIiwgIsOoIjogImUiLCAiw6oiOiAiZSIsICLhur0iOiAiZSIsICLDqyI6ICJlIiwKICAgICAgICAgICAgICLDrSI6ICJpIiwgIsOsIjogImkiLCAiw64iOiAiaSIsICLEqSI6ICJpIiwgIsOvIjogImkiLAogICAgICAgICAgICAgIsOzIjogIm8iLCAiw7IiOiAibyIsICLDtCI6ICJvIiwgIsO1IjogIm8iLCAiw7YiOiAibyIsCiAgICAgICAgICAgICAiw7oiOiAidSIsICLDuSI6ICJ1IiwgIsO7IjogInUiLCAixakiOiAidSIsICLDvCI6ICJ1IiwKICAgICAgICAgICAgICLDvSI6ICJ5In0KICAgIHJldHVybiB0YWJsZS5nZXQoY2gsIGNoKQoKZGVmIF9ub3JtX2xldHRlcihjaCk6CiAgICByZXR1cm4gX3N0cmlwX21hcmtzKGNoKS5sb3dlcigpCgpfQUNDRU5UX1NUUkVTUyA9IHNldCgiw6HDoMOiw6PDqcOow6rhur3DrcOsw67EqcOzw7LDtMO1w7rDucO7xakiKQpfVElMREUgPSBzZXQoIsOj4bq9xKnDtcWpIikKCiMgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tCiMgTsO6Y2xlb3Mgdm9jw6FsaWNvcyAoc8OtbGFiYXMgYXByb3guKS4gVW0gbsO6Y2xlbyA9IHVtYSB2b2dhbCBzaW1wbGVzIE9VIHVtCiMgZGl0b25nby4gRGV2b2x2ZSBsaXN0YSBkZSAoc3RhcnQsZW5kLGJhc2UsaXNfbmFzYWwpLgojIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLQpkZWYgX251Y2xlaSh3b3JkKToKICAgIHcgPSB3b3JkCiAgICBuID0gbGVuKHcpCiAgICBudWNsZWkgPSBbXQogICAgaSA9IDAKICAgIHdoaWxlIGkgPCBuOgogICAgICAgIGNoID0gd1tpXQogICAgICAgIGlmIGNoIGluIF9WT1dFTF9DSEFSUzoKICAgICAgICAgICAgaiA9IGkKICAgICAgICAgICAgd2hpbGUgaiA8IG4gYW5kIHdbal0gaW4gX1ZPV0VMX0NIQVJTOgogICAgICAgICAgICAgICAgaiArPSAxCiAgICAgICAgICAgIHJ1biA9IHdbaTpqXQogICAgICAgICAgICBub3JtX3J1biA9ICIiLmpvaW4oX25vcm1fbGV0dGVyKGMpIGZvciBjIGluIHJ1bikKICAgICAgICAgICAgbmFzYWwgPSBhbnkoYyBpbiBfVElMREUgZm9yIGMgaW4gcnVuKQogICAgICAgICAgICBpZiBsZW4obm9ybV9ydW4pID49IDIgYW5kIG5vcm1fcnVuWzoyXSBpbiBfRElQSFRIT05HOgogICAgICAgICAgICAgICAgYmFzZSA9IF9ESVBIVEhPTkdbbm9ybV9ydW5bOjJdXQogICAgICAgICAgICAgICAgbnVjbGVpLmFwcGVuZCh7InN0YXJ0IjogaSwgImVuZCI6IGosICJiYXNlIjogYmFzZSwKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICJuYXNhbCI6IG5hc2FsLCAibGVuZ3RoIjogbGVuKHJ1bil9KQogICAgICAgICAgICAgICAgaSA9IGoKICAgICAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgICAgIGZvciBrIGluIHJhbmdlKGksIGopOgogICAgICAgICAgICAgICAgYiA9IF9TSU5HTEVbd1trXV0KICAgICAgICAgICAgICAgIGlzX25hc2FsID0gd1trXSBpbiBfVElMREUKICAgICAgICAgICAgICAgIG51Y2xlaS5hcHBlbmQoeyJzdGFydCI6IGssICJlbmQiOiBrICsgMSwgImJhc2UiOiBiLAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIm5hc2FsIjogaXNfbmFzYWwsICJsZW5ndGgiOiAxfSkKICAgICAgICAgICAgaSA9IGoKICAgICAgICAgICAgY29udGludWUKICAgICAgICBpICs9IDEKICAgIHJldHVybiBudWNsZWkKCmRlZiBfc3RyZXNzX2luZGV4KHdvcmQsIG51Y2xlaSk6CiAgICBpZiBub3QgbnVjbGVpOgogICAgICAgIHJldHVybiAtMQogICAgZm9yIGlkeCwgbnUgaW4gZW51bWVyYXRlKG51Y2xlaSk6CiAgICAgICAgc2VnID0gd29yZFtudVsic3RhcnQiXTpudVsiZW5kIl1dCiAgICAgICAgaWYgYW55KGMgaW4gX0FDQ0VOVF9TVFJFU1MgZm9yIGMgaW4gc2VnKToKICAgICAgICAgICAgcmV0dXJuIGlkeAogICAgYmFzZSA9IHdvcmQKICAgIGlmIGJhc2UuZW5kc3dpdGgoInMiKSBhbmQgbGVuKGJhc2UpID4gMToKICAgICAgICBiYXNlID0gYmFzZVs6LTFdCiAgICBsYXN0ID0gYmFzZVstMV0gaWYgYmFzZSBlbHNlICIiCiAgICBlbmRzX3Zvd2VsID0gbGFzdCBpbiBfVk9XRUxfQ0hBUlMKICAgIGVuZHNfbSA9IGJhc2UuZW5kc3dpdGgoIm0iKQogICAgbSA9IGxlbihudWNsZWkpCiAgICBpZiBlbmRzX3Zvd2VsIG9yIGVuZHNfbToKICAgICAgICByZXR1cm4gbWF4KDAsIG0gLSAyKSBpZiBtID49IDIgZWxzZSAwCiAgICBlbHNlOgogICAgICAgIHJldHVybiBtIC0gMQoKX0NPTlMgPSB7CiAgICAicCI6ICJQIiwgImIiOiAiQiIsICJ0IjogIlQiLCAiZCI6ICJEIiwgImsiOiAiSyIsICJnIjogIkciLAogICAgImYiOiAiRiIsICJ2IjogIlYiLCAiaiI6ICJaSCIsICJ6IjogIloiLCAibSI6ICJNIiwgIm4iOiAiTiIsCiAgICAidyI6ICJXIiwgInkiOiAiWSIsCn0KCiMgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tCiMgUGFsYXZyYSAtPiBmb25lbWFzIGJhc2UgKGNvbSBkw61naXRvIGRlIGFjZW50byBqw6EgYXBsaWNhZG8gbmFzIHZvZ2FpcykuCiMgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tCmRlZiBfd29yZF9waG9uZXMod29yZCk6CiAgICB3ID0gd29yZAogICAgbiA9IGxlbih3KQogICAgaSA9IDAKICAgIG51Y2xlaSA9IF9udWNsZWkodykKICAgIHN0cmVzc19pZHggPSBfc3RyZXNzX2luZGV4KHcsIG51Y2xlaSkKICAgIHBob25lbWVzID0gW10KCiAgICB3aGlsZSBpIDwgbjoKICAgICAgICBjaCA9IHdbaV0KICAgICAgICBueHQgPSB3W2kgKyAxXSBpZiBpICsgMSA8IG4gZWxzZSAiIgogICAgICAgIHR3byA9IGNoICsgbnh0CgogICAgICAgIGlmIHR3byA9PSAiY2giOiBwaG9uZW1lcy5hcHBlbmQoIlNIIik7IGkgKz0gMjsgY29udGludWUKICAgICAgICBpZiB0d28gPT0gIm5oIjogcGhvbmVtZXMuYXBwZW5kKCJOIik7IGkgKz0gMjsgY29udGludWUKICAgICAgICBpZiB0d28gPT0gImxoIjogcGhvbmVtZXMuYXBwZW5kKCJMIik7IGkgKz0gMjsgY29udGludWUKICAgICAgICBpZiB0d28gPT0gInJyIjogcGhvbmVtZXMuYXBwZW5kKCJISCIpOyBpICs9IDI7IGNvbnRpbnVlCiAgICAgICAgaWYgdHdvID09ICJzcyI6IHBob25lbWVzLmFwcGVuZCgiUyIpOyBpICs9IDI7IGNvbnRpbnVlCiAgICAgICAgaWYgdHdvID09ICJzaCI6IHBob25lbWVzLmFwcGVuZCgiU0giKTsgaSArPSAyOyBjb250aW51ZQoKICAgICAgICBpZiB0d28gaW4gKCJndSIsICJxdSIpOgogICAgICAgICAgICBhZnRlciA9IHdbaSArIDJdIGlmIGkgKyAyIDwgbiBlbHNlICIiCiAgICAgICAgICAgIGlmIGFmdGVyIGluICJlacOpw6rEqSI6CiAgICAgICAgICAgICAgICBwaG9uZW1lcy5hcHBlbmQoIkciIGlmIGNoID09ICJnIiBlbHNlICJLIik7IGkgKz0gMjsgY29udGludWUKICAgICAgICAgICAgZWxzZToKICAgICAgICAgICAgICAgIHBob25lbWVzLmFwcGVuZCgiRyIgaWYgY2ggPT0gImciIGVsc2UgIksiKQogICAgICAgICAgICAgICAgaWYgbnh0ID09ICJ1IiBhbmQgYWZ0ZXI6CiAgICAgICAgICAgICAgICAgICAgcGhvbmVtZXMuYXBwZW5kKCJXIikKICAgICAgICAgICAgICAgIGkgKz0gMjsgY29udGludWUKCiAgICAgICAgaWYgY2ggaW4gX1ZPV0VMX0NIQVJTOgogICAgICAgICAgICBudSA9IE5vbmUKICAgICAgICAgICAgZm9yIGlkeCwgeHggaW4gZW51bWVyYXRlKG51Y2xlaSk6CiAgICAgICAgICAgICAgICBpZiB4eFsic3RhcnQiXSA8PSBpIDwgeHhbImVuZCJdOgogICAgICAgICAgICAgICAgICAgIG51ID0gKGlkeCwgeHgpOyBicmVhawogICAgICAgICAgICBpZiBudSBpcyBOb25lOgogICAgICAgICAgICAgICAgcGhvbmVtZXMuYXBwZW5kKF9TSU5HTEUuZ2V0KGNoLCAiVU5LIikpOyBpICs9IDE7IGNvbnRpbnVlCiAgICAgICAgICAgIGlkeCwgeHggPSBudQogICAgICAgICAgICBkaWdpdCA9ICIxIiBpZiBpZHggPT0gc3RyZXNzX2lkeCBlbHNlICIwIgogICAgICAgICAgICBiYXNlID0geHhbImJhc2UiXQogICAgICAgICAgICBpZiBiYXNlIGluICgiQUEiLCAiRVkiLCAiRUgiLCAiSVkiLCAiT1ciLCAiQU8iLCAiVVciLCAiQVkiLCAiQVciLCAiT1kiKToKICAgICAgICAgICAgICAgIHBob25lbWVzLmFwcGVuZChiYXNlICsgZGlnaXQpCiAgICAgICAgICAgIGVsc2U6CiAgICAgICAgICAgICAgICBwaG9uZW1lcy5hcHBlbmQoYmFzZSkKICAgICAgICAgICAgaWYgeHhbIm5hc2FsIl06CiAgICAgICAgICAgICAgICBwaG9uZW1lcy5hcHBlbmQoIk4iKQogICAgICAgICAgICBpID0geHhbImVuZCJdCiAgICAgICAgICAgIGNvbnRpbnVlCgogICAgICAgICMgJ2wnIGZpbmFsIGRlIHPDrWxhYmEvcGFsYXZyYSA9PiBXICh2b2NhbGl6YcOnw6NvIHBhdWxpc3RhL2NhcmlvY2EpCiAgICAgICAgaWYgY2ggPT0gImwiOgogICAgICAgICAgICBpZiBpID09IG4gLSAxIG9yIG54dCBub3QgaW4gX1ZPV0VMX0NIQVJTOgogICAgICAgICAgICAgICAgcGhvbmVtZXMuYXBwZW5kKCJXIikKICAgICAgICAgICAgZWxzZToKICAgICAgICAgICAgICAgIHBob25lbWVzLmFwcGVuZCgiTCIpCiAgICAgICAgICAgIGkgKz0gMTsgY29udGludWUKCiAgICAgICAgaWYgY2ggaW4gInBidGRrZnZnanptbncgeSIucmVwbGFjZSgiICIsICIiKToKICAgICAgICAgICAgcGhvbmVtZXMuYXBwZW5kKF9DT05TW2NoXSk7IGkgKz0gMTsgY29udGludWUKCiAgICAgICAgIyAnaCcgbXVkbyAoZXhjZXRvIGVtIGNoL25oL2xoL3NoIGrDoSB0cmF0YWRvcykKICAgICAgICBpZiBjaCA9PSAiaCI6CiAgICAgICAgICAgIGkgKz0gMTsgY29udGludWUKCiAgICAgICAgaWYgY2ggPT0gImMiOgogICAgICAgICAgICBwaG9uZW1lcy5hcHBlbmQoIlMiIGlmIG54dCBpbiAiZWnDqcOqxKkiIGVsc2UgIksiKTsgaSArPSAxOyBjb250aW51ZQogICAgICAgIGlmIGNoID09ICLDpyI6CiAgICAgICAgICAgIHBob25lbWVzLmFwcGVuZCgiUyIpOyBpICs9IDE7IGNvbnRpbnVlCiAgICAgICAgaWYgY2ggPT0gImciOgogICAgICAgICAgICBwaG9uZW1lcy5hcHBlbmQoIlpIIiBpZiBueHQgaW4gImVpw6nDqsSpIiBlbHNlICJHIik7IGkgKz0gMTsgY29udGludWUKCiAgICAgICAgaWYgY2ggPT0gInMiOgogICAgICAgICAgICBwcmV2ID0gd1tpIC0gMV0gaWYgaSA+IDAgZWxzZSAiIgogICAgICAgICAgICBpZiBpID09IDA6IHBob25lbWVzLmFwcGVuZCgiUyIpCiAgICAgICAgICAgIGVsaWYgcHJldiBpbiBfVk9XRUxfQ0hBUlMgYW5kIG54dCBpbiBfVk9XRUxfQ0hBUlM6IHBob25lbWVzLmFwcGVuZCgiWiIpCiAgICAgICAgICAgIGVsaWYgcHJldiBpbiBfVk9XRUxfQ0hBUlMgYW5kIG54dCBpbiAiYnZkZ3pqbW5scnciOiBwaG9uZW1lcy5hcHBlbmQoIloiKQogICAgICAgICAgICBlbGlmIHByZXYgaW4gX1ZPV0VMX0NIQVJTIGFuZCBpID09IG4gLSAxOiBwaG9uZW1lcy5hcHBlbmQoIlMiKQogICAgICAgICAgICBlbHNlOiBwaG9uZW1lcy5hcHBlbmQoIlMiKQogICAgICAgICAgICBpICs9IDE7IGNvbnRpbnVlCgogICAgICAgIGlmIGNoID09ICJ4IjoKICAgICAgICAgICAgcHJldiA9IHdbaSAtIDFdIGlmIGkgPiAwIGVsc2UgIiIKICAgICAgICAgICAgaWYgaSA9PSAwOiBwaG9uZW1lcy5hcHBlbmQoIlNIIikKICAgICAgICAgICAgZWxpZiBwcmV2ID09ICJlIiBhbmQgbnh0IGluIF9WT1dFTF9DSEFSUzogcGhvbmVtZXMuYXBwZW5kKCJaIikKICAgICAgICAgICAgZWxzZTogcGhvbmVtZXMuYXBwZW5kKCJTIikKICAgICAgICAgICAgaSArPSAxOyBjb250aW51ZQoKICAgICAgICBpZiBjaCA9PSAiciI6CiAgICAgICAgICAgIHByZXYgPSB3W2kgLSAxXSBpZiBpID4gMCBlbHNlICIiCiAgICAgICAgICAgIGlmIGkgPT0gMCBvciBwcmV2IG5vdCBpbiBfVk9XRUxfQ0hBUlM6IHBob25lbWVzLmFwcGVuZCgiSEgiKQogICAgICAgICAgICBlbHNlOiBwaG9uZW1lcy5hcHBlbmQoIlIiKQogICAgICAgICAgICBpICs9IDE7IGNvbnRpbnVlCgogICAgICAgIGlmIGNoLmlzYWxwaGEoKToKICAgICAgICAgICAgcGhvbmVtZXMuYXBwZW5kKF9TSU5HTEUuZ2V0KGNoLCAiVU5LIikpCiAgICAgICAgaSArPSAxCiAgICByZXR1cm4gcGhvbmVtZXMKCiMgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tCiMgQVBJCiMgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tCmRlZiBfbm9ybV90ZXh0KHRleHQpOgogICAgcmV0dXJuIHJlLnN1YihyIlxzKyIsICIgIiwgdGV4dC5zdHJpcCgpKQoKZGVmIF9zcGxpdCh0ZXh0KToKICAgIHJldHVybiByZS5maW5kYWxsKHIiW0EtWmEtesOALcO/XVtBLVphLXrDgC3Dv10qfFswLTldK3xbLiwhPzs64oCmXC1dIiwgdGV4dCkKCmRlZiBfbnVtX3RvX3dvcmRzKG51bV9zdHIpOgogICAgIiIiRXhwYW5zw6NvIHNpbXBsZXMgZGUgbsO6bWVyb3MgcGFyYSBwYWxhdnJhcyBlbSBwb3J0dWd1w6pzICgwLi45OTkuOTk5KS4iIiIKICAgIG4gPSBpbnQobnVtX3N0cikKICAgIGlmIG4gPT0gMDoKICAgICAgICByZXR1cm4gWyJ6ZXJvIl0KICAgIHVuaXRzID0gWyIiLCAidW0iLCAiZG9pcyIsICJ0csOqcyIsICJxdWF0cm8iLCAiY2luY28iLCAic2VpcyIsICJzZXRlIiwKICAgICAgICAgICAgICJvaXRvIiwgIm5vdmUiLCAiZGV6IiwgIm9uemUiLCAiZG96ZSIsICJ0cmV6ZSIsICJjYXRvcnplIiwKICAgICAgICAgICAgICJxdWluemUiLCAiZGV6ZXNzZWlzIiwgImRlemVzc2V0ZSIsICJkZXpvaXRvIiwgImRlemVub3ZlIl0KICAgIHRlbnMgPSBbIiIsICIiLCAidmludGUiLCAidHJpbnRhIiwgInF1YXJlbnRhIiwgImNpbnF1ZW50YSIsCiAgICAgICAgICAgICJzZXNzZW50YSIsICJzZXRlbnRhIiwgIm9pdGVudGEiLCAibm92ZW50YSJdCiAgICBodW5kcmVkcyA9IFsiIiwgImNlbSIsICJkdXplbnRvcyIsICJ0cmV6ZW50b3MiLCAicXVhdHJvY2VudG9zIiwKICAgICAgICAgICAgICAgICJxdWluaGVudG9zIiwgInNlaXNjZW50b3MiLCAic2V0ZWNlbnRvcyIsICJvaXRvY2VudG9zIiwKICAgICAgICAgICAgICAgICJub3ZlY2VudG9zIl0KICAgIHdvcmRzID0gW10KICAgIGlmIG4gPj0gMTAwMDoKICAgICAgICB0aG91c2FuZHMgPSBuIC8vIDEwMDAKICAgICAgICBpZiB0aG91c2FuZHMgPT0gMToKICAgICAgICAgICAgd29yZHMuYXBwZW5kKCJtaWwiKQogICAgICAgIGVsc2U6CiAgICAgICAgICAgIHdvcmRzLmV4dGVuZChfbnVtX3RvX3dvcmRzX3VuZGVyXzEwMDAodGhvdXNhbmRzKSArIFsibWlsIl0pCiAgICAgICAgbiAlPSAxMDAwCiAgICB3b3Jkcy5leHRlbmQoX251bV90b193b3Jkc191bmRlcl8xMDAwKG4pKQogICAgcmV0dXJuIHdvcmRzCgpkZWYgX251bV90b193b3Jkc191bmRlcl8xMDAwKG4pOgogICAgdW5pdHMgPSBbIiIsICJ1bSIsICJkb2lzIiwgInRyw6pzIiwgInF1YXRybyIsICJjaW5jbyIsICJzZWlzIiwgInNldGUiLAogICAgICAgICAgICAgIm9pdG8iLCAibm92ZSIsICJkZXoiLCAib256ZSIsICJkb3plIiwgInRyZXplIiwgImNhdG9yemUiLAogICAgICAgICAgICAgInF1aW56ZSIsICJkZXplc3NlaXMiLCAiZGV6ZXNzZXRlIiwgImRlem9pdG8iLCAiZGV6ZW5vdmUiXQogICAgdGVucyA9IFsiIiwgIiIsICJ2aW50ZSIsICJ0cmludGEiLCAicXVhcmVudGEiLCAiY2lucXVlbnRhIiwKICAgICAgICAgICAgInNlc3NlbnRhIiwgInNldGVudGEiLCAib2l0ZW50YSIsICJub3ZlbnRhIl0KICAgIGh1bmRyZWRzID0gWyIiLCAiY2VtIiwgImR1emVudG9zIiwgInRyZXplbnRvcyIsICJxdWF0cm9jZW50b3MiLAogICAgICAgICAgICAgICAgInF1aW5oZW50b3MiLCAic2Vpc2NlbnRvcyIsICJzZXRlY2VudG9zIiwgIm9pdG9jZW50b3MiLAogICAgICAgICAgICAgICAgIm5vdmVjZW50b3MiXQogICAgcmVzID0gW10KICAgIGggPSBuIC8vIDEwMAogICAgciA9IG4gJSAxMDAKICAgIGlmIGg6CiAgICAgICAgaWYgaCA9PSAxIGFuZCByID09IDA6CiAgICAgICAgICAgIHJlcy5hcHBlbmQoImNlbSIpCiAgICAgICAgZWxzZToKICAgICAgICAgICAgcmVzLmFwcGVuZChodW5kcmVkc1toXSkKICAgIGlmIHI6CiAgICAgICAgaWYgciA8IDIwOgogICAgICAgICAgICByZXMuYXBwZW5kKHVuaXRzW3JdKQogICAgICAgIGVsc2U6CiAgICAgICAgICAgIHQgPSByIC8vIDEwCiAgICAgICAgICAgIHUgPSByICUgMTAKICAgICAgICAgICAgaWYgdToKICAgICAgICAgICAgICAgIHJlcy5hcHBlbmQodGVuc1t0XSArICIgZSAiICsgdW5pdHNbdV0pCiAgICAgICAgICAgIGVsc2U6CiAgICAgICAgICAgICAgICByZXMuYXBwZW5kKHRlbnNbdF0pCiAgICByZXR1cm4gcmVzCgpfVkFMSUQgPSBOb25lCgpkZWYgX2xvYWRfc3ltYm9scygpOgogICAgZ2xvYmFsIF9WQUxJRAogICAgaWYgX1ZBTElEIGlzIG5vdCBOb25lOgogICAgICAgIHJldHVybgogICAgdHJ5OgogICAgICAgIGZyb20gdGV4dC5zeW1ib2xzMiBpbXBvcnQgc3ltYm9scyBhcyBfcwogICAgICAgIF9WQUxJRCA9IHNldChfcykKICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgX1ZBTElEID0gc2V0KCJQIEIgVCBEIEsgRyBGIFYgUyBaIE0gTiBMIFIgVyBZIi5zcGxpdCgpKQogICAgICAgIF9WQUxJRCB8PSB7IkFBMCIsIkFBMSIsIkFBMiIsIkVIMCIsIkVIMSIsIkVIMiIsIkVZMCIsIkVZMSIsIkVZMiIsCiAgICAgICAgICAgICAgICAgICAiSVkwIiwiSVkxIiwiSVkyIiwiT1cwIiwiT1cxIiwiT1cyIiwiQU8wIiwiQU8xIiwiQU8yIiwKICAgICAgICAgICAgICAgICAgICJVVzAiLCJVVzEiLCJVVzIiLCJBSDAiLCJBSDEiLCJBSDIiLCJFUjAiLCJFUjEiLCJFUjIiLAogICAgICAgICAgICAgICAgICAgIklIMCIsIklIMSIsIklIMiIsIkFZMCIsIkFZMSIsIkFZMiIsIkFXMCIsIkFXMSIsIkFXMiIsCiAgICAgICAgICAgICAgICAgICAiT1kwIiwiT1kxIiwiT1kyIiwiU0giLCJaSCIsIkNIIiwiSkgiLCJESCIsIlRIIiwiSEgiLCJORyIsCiAgICAgICAgICAgICAgICAgICAiVU5LIiwiU1AiLCJTUDIiLCJTUDMiLCIsIiwiLiIsIiEiLCI/Iiwi4oCmIiwiLSIsIkFBIiwiRVIiLCJJSCJ9CgpkZWYgX3ZhbGlkYXRlKHApOgogICAgcmV0dXJuIHAgaWYgcCBpbiBfVkFMSUQgZWxzZSAiVU5LIgoKZGVmIHRleHRfbm9ybWFsaXplKHRleHQpOgogICAgcmV0dXJuIF9ub3JtX3RleHQodGV4dCkKCmRlZiBnMnAodGV4dCk6CiAgICBfbG9hZF9zeW1ib2xzKCkKICAgIHRva2VucyA9IF9zcGxpdCh0ZXh0KQogICAgcGhvbmVzID0gW10KICAgIHByZXZfd29yZCA9IEZhbHNlCiAgICBmb3IgdG9rIGluIHRva2VuczoKICAgICAgICBpZiB0b2sgaW4gIi4sIT874oCmIiBvciB0b2sgPT0gIi0iOgogICAgICAgICAgICBwaG9uZXMuYXBwZW5kKHsiLiI6ICIuIiwgIiwiOiAiLCIsICIhIjogIiEiLCAiPyI6ICI/IiwKICAgICAgICAgICAgICAgICAgICAgICAgICAgIuKApiI6ICLigKYiLCAiLSI6ICItIiwgIjsiOiAiLiIsICI6IjogIi4ifS5nZXQodG9rLCAiLCIpKQogICAgICAgICAgICBwcmV2X3dvcmQgPSBGYWxzZQogICAgICAgICAgICBjb250aW51ZQogICAgICAgIGlmIHRvay5pc2RpZ2l0KCk6CiAgICAgICAgICAgIGZvciB3IGluIF9udW1fdG9fd29yZHModG9rKToKICAgICAgICAgICAgICAgIGlmIHc6CiAgICAgICAgICAgICAgICAgICAgcGhvbmVzLmV4dGVuZChfdmFsaWRhdGUocCkgZm9yIHAgaW4gX3dvcmRfcGhvbmVzKHcpKQogICAgICAgICAgICBwcmV2X3dvcmQgPSBUcnVlCiAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgaWYgbm90IHJlLnNlYXJjaChyIlthLXrDoC3Dv10iLCB0b2subG93ZXIoKSk6CiAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgIyBOb3RhOiBuw6NvIGluc2VyaW1vcyBlc3Bhw6dvIGVudHJlIHBhbGF2cmFzIOKAlCBvIGNsZWFuX3RleHQgZG8KICAgICAgICAjIEdQVC1Tb1ZJVFMgZGVzY2FydGEvcXVlYnJhIGVtIHPDrW1ib2xvIGludsOhbGlkbzsgZSBvIHBpcGVsaW5lIGRlCiAgICAgICAgIyBUVFMgdXNhIGEgc2VxdcOqbmNpYSBjb250w61ndWEgZGUgZm9uZW1hcyAoY29tbyBvIG3Ds2R1bG8gZGUgaW5nbMOqcykuCiAgICAgICAgcGhvbmVzLmV4dGVuZChfdmFsaWRhdGUocCkgZm9yIHAgaW4gX3dvcmRfcGhvbmVzKHRvay5sb3dlcigpKSkKICAgICAgICBwcmV2X3dvcmQgPSBUcnVlCiAgICByZXR1cm4gcGhvbmVzCgppZiBfX25hbWVfXyA9PSAiX19tYWluX18iOgogICAgdGVzdHMgPSBbIk9sw6EsIHR1ZG8gYmVtPyBFdSBzb3UgYSBMaWEuIiwgIm1ldSIsICJtw6NlIiwgIm7Do28iLCAicG9ydHVndcOqcyIsCiAgICAgICAgICAgICAiY2FzYSIsICJjYWNob3JybyIsICJjaGF2ZSIsICJndWVycmEiLCAicXVlaWpvIiwgInF1YXRybyIsCiAgICAgICAgICAgICAiYnJhc2lsZWlybyIsICJSaW9kZUphbmVpcm8iLCAiU8Ojb1BhdWxvIiwgImZlbGljaWRhZGUiLCAiYW1vciIsCiAgICAgICAgICAgICAiY29yYcOnw6NvIiwgImdlbnRlIiwgImZ1bsOnw6NvIiwgImV4ZW1wbG8iLCAidGF4YSIsICJzYWJpYSIsICJkZXoiLAogICAgICAgICAgICAgImx1eiIsICJkaWEiLCAibm9pdGUiLCAibXVsaGVyIiwgInRyYWJhbGhvIiwgInVuaXZlcnNpZGFkZSIsCiAgICAgICAgICAgICAib2JyaWdhZG8iLCAidm9jw6oiLCAiZWxhIiwgImVsZXMiLCAicGVxdWVubyIsICJsZWl0ZSIsICJncmFuZGUiLAogICAgICAgICAgICAgIm11bmRvIiwgImZhbGFyIiwgInZlcmRhZGUiLCAiaGlzdMOzcmlhIiwgInDDo28iLCAibcOjbyJdCiAgICBfbG9hZF9zeW1ib2xzKCkKICAgIGZvciB3IGluIHRlc3RzOgogICAgICAgIHBoID0gZzJwKHcpCiAgICAgICAgYmFkID0gW3AgZm9yIHAgaW4gcGggaWYgcCBub3QgaW4gX1ZBTElEXQogICAgICAgIHByaW50KGYie3chcjoyNH0ge3BofSAgeychISAnK3N0cihiYWQpIGlmIGJhZCBlbHNlICcnfSIpCg=="


def _module_src():
    return base64.b64decode(PORTUGUESE_B64).decode("utf-8")


def _bak(path):
    bak = path + ".bak_pt"
    if not os.path.exists(bak):
        try:
            shutil.copy2(path, bak)
            print("[PATCH] backup -> %s" % os.path.basename(bak))
        except Exception as e:
            print("[PATCH] aviso: falha no backup (%s)" % e)


def _read(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def _write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def install_module(repo):
    dst = os.path.join(repo, "GPT_SoVITS", "text", "portuguese.py")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst):
        existing = _read(dst)
        if "def g2p" in existing and "def text_normalize" in existing:
            print("[PATCH] portuguese.py ja existe (skip).")
            return True
    _write(dst, _module_src())
    print("[PATCH] portuguese.py instalado em %s" % os.path.relpath(dst, repo))
    return True


def patch_cleaner(repo):
    path = os.path.join(repo, "GPT_SoVITS", "text", "cleaner.py")
    if not os.path.exists(path):
        print("[PATCH] cleaner.py NAO ENCONTRADO: %s" % path)
        return False
    _bak(path)
    text = _read(path)
    if "portuguese" in text:
        print("[PATCH] cleaner: mapa ja tem 'pt' (skip).")
        return True

    def _repl(m):
        line = m.group(0)
        if "portuguese" in line or '"pt"' in line or "'pt'" in line:
            return line
        idx = line.rfind("}")
        if idx == -1:
            return line
        return line[:idx] + ', "pt": "portuguese"' + line[idx:]

    new_text = re.sub(r'(\s*)language_module_map\s*=\s*\{[^\n]*\}', _repl, text)
    if new_text == text:
        print("[PATCH] cleaner: ANCTOR NAO ENCONTRADA (language_module_map).")
        return False
    _write(path, new_text)
    print("[PATCH] cleaner: language_module_map atualizado com 'pt'.")
    return True


def _inject_lang(path, anchor, token, label):
    text = _read(path)
    pat = re.compile(anchor + r'\s*:\s*list\s*=\s*\[[^\n]*\]')
    m = pat.search(text)
    if not m:
        print("[PATCH] %s: ANCTOR NAO ENCONTRADA." % label)
        return False
    line = m.group(0)
    if token in line:
        print("[PATCH] %s: ja tem 'pt' nesta lista (skip)." % label)
        return True
    idx = line.rfind("]")
    new_line = line[:idx] + ", " + token + line[idx:]
    _write(path, text[:m.start()] + new_line + text[m.end():])
    print("[PATCH] %s: aplicado." % label)
    return True


def patch_tts(repo):
    path = os.path.join(repo, "GPT_SoVITS", "TTS_infer_pack", "TTS.py")
    if not os.path.exists(path):
        print("[PATCH] TTS.py NAO ENCONTRADO: %s" % path)
        return False
    _bak(path)
    ok = True
    ok &= _inject_lang(path, r'v2_languages', '"pt"', "TTS v2_languages")
    ok &= _inject_lang(path, r'v1_languages', '"pt"', "TTS v1_languages")
    return ok


def patch_textpreprocessor(repo):
    path = os.path.join(repo, "GPT_SoVITS", "TTS_infer_pack", "TextPreprocessor.py")
    if not os.path.exists(path):
        print("[PATCH] TextPreprocessor.py NAO ENCONTRADO: %s" % path)
        return False
    _bak(path)
    text = _read(path)
    if SENT_PT in text:
        print("[PATCH] TextPreprocessor: ja aplicado (skip).")
        return True
    m = re.search(r'^(\s*)elif language == "en":[ \t]*\r?\n', text, re.M)
    if not m:
        print("[PATCH] TextPreprocessor: ANCTOR 'elif language == \"en\"' NAO ENCONTRADA.")
        return False
    ind = m.group(1)
    block = ("%s%s\n" % (ind, SENT_PT)
             + "%selif language == \"pt\":\n" % ind
             + "%s    langlist.append(\"pt\")\n" % ind
             + "%s    textlist.append(text)\n" % ind)
    # Insere ANTES da linha `elif language == "en":` (m.start()), mantendo o
    # corpo do 'en' intacto logo depois.
    text = text[:m.start()] + block + text[m.start():]
    # pre_seg_text: usar pontuação latina (.) para pt (não "。")
    text = text.replace('lang != "en"', 'not (lang in ("en", "pt"))')
    _write(path, text)
    print("[PATCH] TextPreprocessor: branch 'pt' + pontuacao latin aplicados.")
    return True


def patch_get_text(repo):
    path = os.path.join(repo, "GPT_SoVITS", "prepare_datasets", "1-get-text.py")
    if not os.path.exists(path):
        print("[PATCH] 1-get-text.py NAO ENCONTRADO: %s" % path)
        return False
    _bak(path)
    text = _read(path)
    if '"PT": "pt"' in text or SENT_PT in text:
        print("[PATCH] 1-get-text: mapa PT -> pt ja presente (skip).")
        return True
    i = text.find("language_v1_to_language_v2")
    if i == -1:
        print("[PATCH] 1-get-text: ANCTOR NAO ENCONTRADA.")
        return False
    brace = text.find("}", i)
    if brace == -1:
        print("[PATCH] 1-get-text: ANCTOR '}' NAO ENCONTRADA.")
        return False
    ins = '\n        %s\n        "PT": "pt",\n        "pt": "pt",\n' % SENT_PT
    text = text[:brace] + ins + text[brace:]
    _write(path, text)
    print("[PATCH] 1-get-text: mapa PT -> pt aplicado.")
    return True


def run(repo):
    ok = True
    ok &= install_module(repo)
    ok &= patch_cleaner(repo)
    ok &= patch_tts(repo)
    ok &= patch_textpreprocessor(repo)
    ok &= patch_get_text(repo)
    print("PATCH_OK" if ok else "PATCH_INCOMPLETO")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python patch_sovits_pt.py <GPT-SoVITS_root>")
        sys.exit(1)
    run(sys.argv[1])
