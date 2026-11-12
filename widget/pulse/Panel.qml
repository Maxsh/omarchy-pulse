import QtQuick
import qs.Commons as Commons
import qs.Ui

// The pulse summary popup: today's keyboard and mouse totals, one row per
// metric, in theme colors. Data lives in the bar widget (hostWidget), which
// owns fetching — this panel only displays it and asks for a refresh on open.
Panel {
  id: root
  moduleName: "maxsh.pulse"
  manageIpc: false

  property var anchorItem: null

  // The bar tracks the widget mounted in its slot — BarWidget.qml — not this
  // nested panel. Everything the bar identifies a panel by has to be that
  // widget: the popout coordinator compares against slot.activeItem, and
  // switchPanelFrom looks the slot up the same way.
  property var hostWidget: null
  readonly property var barIdentity: hostWidget || root

  // Live mirror of the bar widget's data; bindings update on every refresh.
  readonly property var stats: hostWidget ? hostWidget.today : null
  readonly property string lastError: hostWidget ? hostWidget.lastError : ""
  readonly property string awUrl: hostWidget ? hostWidget.awUrl : ""

  Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }

  function refresh() {
    if (hostWidget && typeof hostWidget.refresh === "function") hostWidget.refresh()
  }

  onOpenedChanged: function() {
    if (opened) refresh()
  }

  // ---- Row component: muted label on the left, value on the right.
  component StatRow: Item {
    id: row
    property string labelText: ""
    property string valueText: ""
    width: parent ? parent.width : 0
    height: Math.max(labelText_.implicitHeight, valueText_.implicitHeight)

    Text {
      id: labelText_
      textFormat: Text.PlainText
      text: row.labelText
      color: Commons.Color.muted
      font.family: Commons.Style.font.family
      font.pixelSize: Commons.Style.font.body
      anchors.left: parent.left
      anchors.verticalCenter: parent.verticalCenter
    }

    Text {
      id: valueText_
      textFormat: Text.PlainText
      text: row.valueText
      color: Commons.Color.popups.text
      font.family: Commons.Style.font.family
      font.pixelSize: Commons.Style.font.body
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      horizontalAlignment: Text.AlignRight
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.barIdentity
    bar: root.bar
    open: root.opened
    // Anchor under the widget rather than the middle of the bar, so the
    // popup follows wherever the widget is placed.
    centerOnBar: false
    focusTarget: panel.loadedContent
    contentWidth: panel.fittedContentWidth(Commons.Style.space(300))
    contentHeight: panel.fittedContentHeight(panel.loadedContentHeight)

    content: PanelKeyCatcher {
      anchors.fill: parent
      onCloseRequested: root.close()

      Column {
        id: contentColumn
        anchors.fill: parent
        spacing: Commons.Style.space(8)

        Text {
          textFormat: Text.PlainText
          text: strings.t("pulse.title")
          color: Commons.Color.popups.text
          font.family: Commons.Style.font.family
          font.pixelSize: Commons.Style.font.body
          font.weight: Font.DemiBold
        }

        Text {
          textFormat: Text.PlainText
          text: strings.t("pulse.subtitle")
          color: Commons.Color.muted
          font.family: Commons.Style.font.family
          font.pixelSize: Commons.Style.font.bodySmall
        }

        Item { width: 1; height: Commons.Style.space(2) }

        StatRow {
          labelText: strings.t("pulse.keyboard")
          valueText: root.stats ? Commons.I18n.formatNumber(root.stats.presses) : "—"
        }

        StatRow {
          labelText: strings.t("pulse.mouse")
          valueText: root.stats ? Commons.I18n.formatNumber(root.stats.clicks) : "—"
        }

        StatRow {
          labelText: strings.t("pulse.scrollLabel")
          valueText: root.stats ? Commons.I18n.formatNumber(root.stats.scrollX + root.stats.scrollY) : "—"
        }

        StatRow {
          labelText: strings.t("pulse.travel")
          valueText: root.stats
            ? strings.tn("pulse.pixel", root.stats.deltaX + root.stats.deltaY).arg(Commons.I18n.formatNumber(root.stats.deltaX + root.stats.deltaY))
            : "—"
        }

        StatRow {
          labelText: strings.t("pulse.active", root.stats ? root.stats.minutes : 0)
          valueText: root.stats ? Commons.I18n.formatNumber(root.stats.minutes) : "—"
        }

        Text {
          width: parent ? parent.width : 0
          visible: root.lastError !== ""
          wrapMode: Text.Wrap
          textFormat: Text.PlainText
          text: root.lastError === "noInputBucket"
            ? strings.t("pulse.error.noInputBucket")
            : strings.t("pulse.error.unreachable").arg(root.awUrl)
          color: Commons.Color.urgent
          font.family: Commons.Style.font.family
          font.pixelSize: Commons.Style.font.bodySmall
        }
      }
    }
  }
}
