"""Responsive scrollable grid for displaying character cards."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget
from qfluentwidgets import FlowLayout, SmoothScrollArea

from .image_card import CharacterCard
from utils import Character


class ImageGrid(SmoothScrollArea):
    """Scrollable container holding CharacterCard widgets in a flow layout."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cards: list[CharacterCard] = []

        self._container = QWidget()
        self._layout = FlowLayout(self._container, needAni=True)
        self._layout.setContentsMargins(12, 12, 12, 12)
        self._layout.setSpacing(10)

        self.setWidget(self._container)
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea { border: none; background: transparent; }")

    def clear_cards(self):
        """Remove all cards from the grid."""
        for card in self.cards:
            self._layout.removeWidget(card)
            card.hide()
            card.deleteLater()
        self.cards.clear()
        self._container.updateGeometry()

    def setup_cards(self, characters: list[Character]):
        """Create cards for the given Character list, clearing any existing ones."""
        self.clear_cards()
        for char in characters:
            card = CharacterCard(
                index=char.index,
                name=char.name,
                description=char.description,
                aliases=char.aliases,
            )
            self.cards.append(card)
            self._layout.addWidget(card)

    def add_cards(self, characters: list[Character]) -> list[CharacterCard]:
        """Add cards without clearing existing ones. Returns created cards."""
        new_cards = []
        for char in characters:
            card = CharacterCard(
                index=char.index,
                name=char.name,
                description=char.description,
                aliases=char.aliases,
            )
            self.cards.append(card)
            self._layout.addWidget(card)
            new_cards.append(card)
        return new_cards

    def get_card(self, index: int) -> CharacterCard | None:
        """Get card by index."""
        if 0 <= index < len(self.cards):
            return self.cards[index]
        return None

    def remove_card(self, index: int):
        """Remove a single card by index."""
        card = self.get_card(index)
        if card:
            self._layout.removeWidget(card)
            card.hide()
            card.deleteLater()
            self.cards.remove(card)
            self._container.updateGeometry()

    def remove_checked(self) -> int:
        """Remove all checked cards. Returns count removed."""
        to_remove = [c for c in self.cards if c.is_checked]
        for card in to_remove:
            self._layout.removeWidget(card)
            card.hide()
            card.deleteLater()
            self.cards.remove(card)
        if to_remove:
            self._container.updateGeometry()
        return len(to_remove)

    @property
    def checked_cards(self) -> list[CharacterCard]:
        """Return list of checked cards that are done."""
        return [c for c in self.cards if c.is_checked and c.state == "done"]

    @property
    def done_cards(self) -> list[CharacterCard]:
        """Return all cards in 'done' state."""
        return [c for c in self.cards if c.state == "done" and c.image_data]

    @property
    def failed_cards(self) -> list[CharacterCard]:
        """Return all cards in 'error' state."""
        return [c for c in self.cards if c.state == "error"]

    def check_all(self):
        for c in self.cards:
            if c.state == "done":
                c.checkbox.setChecked(True)

    def uncheck_all(self):
        for c in self.cards:
            c.checkbox.setChecked(False)

    def check_all_failed(self):
        for c in self.cards:
            if c.state == "error":
                c.checkbox.setChecked(True)
