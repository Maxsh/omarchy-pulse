import QtQuick
import qs.Commons as Commons
import qs.Ui

// The pulse summary popup: today's keyboard/mouse/idle split as percentages
// of the session so far, a large stacked bar, and per-metric rows with color
// swatches matching the bar. Data lives in the bar widget (hostWidget),
// which owns fetching — this panel only displays it and asks for a refresh
// on open. Absolute counts are intentionally not shown (relative values
// only, per the product goal).
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
  readonly property var stats: hostWidget ? hostWidget.activity : null
  readonly property string lastError: hostWidget ? hostWidget.lastError : ""
  readonly property string awUrl: hostWidget ? hostWidget.awUrl : ""
  readonly property bool hasData: stats !== null && stats.spanMinutes > 0

  readonly property color kbColor: hostWidget ? hostWidget.kbColor : Commons.Color.accent
  readonly property color mouseColor: hostWidget ? hostWidget.mouseColor : Commons.Util.alpha(Commons.Color.accent, 0.45)
  readonly property color idleColor: hostWidget ? hostWidget.idleColor : Commons.Util.alpha(Commons.Color.accent, 0.15)

  Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }

  function refresh() {
    if (hostWidget && typeof hostWidget.refresh === "function") hostWidget.refresh()
  }

  function formatTime(ms) {
    var locale = Qt.locale(Commons.I18n.formatLocale)
    return new Date(ms).toLocaleTimeString(locale, "HH:mm")
  }

  onOpenedChanged: function() {
    if (opened) refresh()
  }

  // ---- Percentage row: color swatch, muted label, right-aligned value.
  component PctRow: Item {
    id: row
    property color swatchColor: Commons.Color.accent
    property string labelText: ""
    property string valueText: ""
    width: parent ? parent.width : 0
    height: Math.max(swatch.implicitHeight, labelText_.implicitHeight)

    Rectangle {
      id: swatch
      width: Style.space(10)
      height: Style.space(10)
      radius: Style.space(2)
      color: row.swatchColor
      anchors.left: parent.left
      anchors.verticalCenter: parent.verticalCenter
    }

    Text {
      id: labelText_
      textFormat: Text.PlainText
      text: row.labelText
      color: Commons.Color.popups.text
      font.family: Style.font.family
      font.pixelSize: Style.font.body
      anchors.left: swatch.right
      anchors.leftMargin: Style.space(8)
      anchors.verticalCenter: parent.verticalCenter
    }

    Text {
      id: valueText_
      textFormat: Text.PlainText
      text: row.valueText
      color: Commons.Color.popups.text
      font.family: Style.font.family
      font.pixelSize: Style.font.body
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
    contentWidth: panel.fittedContentWidth(Style.space(280))
    contentHeight: panel.fittedContentHeight(panel.loadedContentHeight)

    content: PanelKeyCatcher {
      anchors.fill: parent
      onCloseRequested: root.close()

      Column {
        id: contentColumn
        anchors.fill: parent
        spacing: Style.space(10)

        Text {
          textFormat: Text.PlainText
          text: strings.t("pulse.title")
          color: Commons.Color.popups.text
          font.family: Style.font.family
          font.pixelSize: Style.font.body
          font.weight: Font.DemiBold
        }

        Text {
          textFormat: Text.PlainText
          text: root.hasData
            ? strings.t("pulse.since").arg(root.formatTime(root.stats.firstTsMs))
            : strings.t("pulse.subtitle")
          color: Commons.Color.muted
          font.family: Style.font.family
          font.pixelSize: Style.font.bodySmall
        }

        // Large stacked bar: idle fills the pill, keyboard and mouse stack
        // over it from the left — the same proportions as the bar widget.
        Item {
          width: parent ? parent.width : 0
          height: Style.space(14)

          Rectangle {
            anchors.fill: parent
            radius: Style.space(3)
            color: root.idleColor
          }

          Rectangle {
            id: bigKb
            x: 0
            width: parent.width * (root.hasData ? root.stats.kbPct : 0) / 100.0
            height: parent.height
            radius: Style.space(3)
            color: root.kbColor
          }

          Rectangle {
            id: bigMouse
            x: bigKb.width
            width: parent.width * (root.hasData ? root.stats.mousePct : 0) / 100.0
            height: parent.height
            radius: Style.space(3)
            color: root.mouseColor
          }
        }

        PctRow {
          swatchColor: root.kbColor
          labelText: strings.t("pulse.keyboard")
          valueText: root.hasData ? Commons.I18n.formatNumber(root.stats.kbPct) + "%" : "—"
        }

        PctRow {
          swatchColor: root.mouseColor
          labelText: strings.t("pulse.mouse")
          valueText: root.hasData ? Commons.I18n.formatNumber(root.stats.mousePct) + "%" : "—"
        }

        PctRow {
          swatchColor: root.idleColor
          labelText: strings.t("pulse.idle")
          valueText: root.hasData ? Commons.I18n.formatNumber(root.stats.idlePct) + "%" : "—"
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
          font.family: Style.font.family
          font.pixelSize: Style.font.bodySmall
        }
      }
    }
  }
}
