"""A minimal fake WebElement wrapper backed by xml.etree.ElementTree.

This provides a tiny subset of the Selenium WebElement API used by the
parsing helpers in CaseScraperService: `find_element`, `find_elements`,
`text`, and `get_attribute` for simple cases.
"""
from __future__ import annotations

from typing import List, Optional
import xml.etree.ElementTree as ET


class FakeWebElement:
    def __init__(self, element: ET.Element, root: Optional[ET.Element] = None):
        self._el = element
        # Keep reference to top-level root to support ancestor/sibling helpers
        self._root = root if root is not None else element

    @property
    def text(self) -> str:
        return "".join(self._el.itertext()).strip()

    def get_attribute(self, name: str) -> Optional[str]:
        if name == "outerHTML":
            return ET.tostring(self._el, encoding="unicode")
        if name == "innerHTML":
            return "".join(ET.tostring(e, encoding="unicode") for e in list(self._el))
        return self._el.attrib.get(name)

    def find_elements(self, by, selector) -> List["FakeWebElement"]:
        # Support By.TAG_NAME and simple XPath starting with .//tag
        if selector is None:
            return []
        sel = selector
        if sel.startswith(".//"):
            tag = sel[3:]
            elems = self._el.findall('.//' + tag)
            return [FakeWebElement(e, root=self._root) for e in elems]
        # tag name
        elems = self._el.findall('.//' + sel)
        return [FakeWebElement(e, root=self._root) for e in elems]

    def find_element(self, by, selector) -> "FakeWebElement":
        # ID lookup
        if by == "id" or (isinstance(selector, str) and not selector.startswith(".//") and selector.isidentifier() is False and selector.startswith("#")):
            sid = selector.lstrip('#')
            for e in self._root.iter():
                if e.get('id') == sid:
                    return FakeWebElement(e, root=self._root)
            raise Exception(f"Element with id={sid} not found")

        # Handle simple XPath axes used by parser: following-sibling::dd[1], ancestor::p[1]
        if selector.startswith('following-sibling::'):
            # e.g. 'following-sibling::dd[1]'
            parts = selector.split('::', 1)[1]
            tag = parts.split('[')[0]
            # Find parent by scanning root
            parent = _find_parent(self._root, self._el)
            if parent is None:
                raise Exception('No parent found for following-sibling lookup')
            found = None
            seen = False
            for child in list(parent):
                if seen and child.tag == tag:
                    found = child
                    break
                if child is self._el:
                    seen = True
            if found is None:
                raise Exception(f"No following-sibling {tag} found")
            return FakeWebElement(found, root=self._root)

        if selector.startswith('ancestor::'):
            # e.g. 'ancestor::p[1]'
            anc = selector.split('::', 1)[1]
            tag = anc.split('[')[0]
            parent = _find_parent(self._root, self._el)
            while parent is not None:
                if parent.tag == tag:
                    return FakeWebElement(parent, root=self._root)
                parent = _find_parent(self._root, parent)
            raise Exception(f"Ancestor {tag} not found")

        if selector.startswith('.//'):
            tag = selector[3:]
            found = self._el.find('.//' + tag)
            if found is None:
                raise Exception(f"No element for xpath {selector}")
            return FakeWebElement(found, root=self._root)

        # tag name
        found = self._el.find('.//' + selector)
        if found is None:
            raise Exception(f"No element for tag {selector}")
        return FakeWebElement(found, root=self._root)


def _find_parent(root: ET.Element, target: ET.Element) -> Optional[ET.Element]:
    # Recursively find parent of target under root
    for parent in root.iter():
        for child in list(parent):
            if child is target:
                return parent
    return None
