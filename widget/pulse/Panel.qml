import QtQuick
import qs.Commons as Commons
import qs.Ui

// The pulse summary popup.
//
//   Pulse                                                    [refresh]
//   Since 19:50
//   Keyboard 19% · Mouse 9% · Idle 72%   (swatch rows, live)
//   LAST 7 DAYS
//   Mon ▓▓▓░░░  …  Sun ▓▓▓░░░            (hover: exact percentages)
//   TOTAL
//   ▓▓▓▓░░░░░░
//
// Data lives in the bar widget (hostWidget), which owns fetching: the bar's
// 60 s poll keeps today fresh, and opening the panel (or the refresh button)
// fetches the whole week. Absolute counts are intentionally not shown —
// relative values only, per the product goal.
Panel {
  id: root
  moduleName: "maxsh.pulse"
  ipcTarget: "maxsh.pulse"

  property var anchorItem: null

  // The bar tracks the widget mounted in its slot — BarWidget.qml — not this
  // nested panel. Everything the bar identifies a panel by has to be that
  // widget: the popout coordinator compares against slot.activeItem, and
  // switchPanelFrom looks the slot up the same way.
  property var hostWidget: null
  readonly property var barIdentity: hostWidget || root

  // Live mirror of the bar widget's data; bindings update on every refresh.
  readonly property var stats: hostWidget ? hostWidget.activity : null
  readonly property var days: hostWidget && hostWidget.week ? hostWidget.week.days : []
  readonly property var total: hostWidget && hostWidget.week ? hostWidget.week.total : null
  readonly property string lastError: hostWidget ? hostWidget.lastError : ""
  readonly property string awUrl: hostWidget ? hostWidget.awUrl : ""
  readonly property bool hasData: stats !== null && stats.spanMinutes > 0

  readonly property color kbColor: hostWidget ? hostWidget.kbColor : Commons.Color.accent
  readonly property color mouseColor: hostWidget ? hostWidget.mouseColor : Commons.Util.alpha(Commons.Color.accent, 0.45)
  readonly property color idleColor: hostWidget ? hostWidget.idleColor : Commons.Util.alpha(Commons.Color.accent, 0.15)

  Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }

  // Opening the panel (or the refresh button) pulls the whole week; the
  // fetch also refreshes today, which the bar's poll keeps alive meanwhile.
  function refresh() {
    if (hostWidget && typeof hostWidget.refreshWeek === "function") hostWidget.refreshWeek()
  }

  function formatTime(ms) {
    var locale = Qt.locale(Commons.I18n.formatLocale)
    return new Date(ms).toLocaleTimeString(locale, "HH:mm")
  }

  function pctText(day) {
    return strings.t("pulse.keyboard") + " " + Commons.I18n.formatNumber(day.kbPct) + "% · "
      + strings.t("pulse.mouse") + " " + Commons.I18n.formatNumber(day.mousePct) + "% · "
      + strings.t("pulse.idle") + " " + Commons.I18n.formatNumber(day.idlePct) + "%"
  }

  onOpenedChanged: function() {
    if (opened) refresh()
  }

  // ---- Percentage row: color swatch, label, right-aligned value.
  component PctRow: Item {
    id: row
    property color swatchColor: Commons.Color.accent
    property string labelText: ""
    property string valueText: ""
    width: parent ? parent.width : 0
    height: Math.max(swatch.implicitHeight, labelText_.implicitHeight)

    Rectangle {
      id: swatch
      width: Commons.Style.space(10)
      height: Commons.Style.space(10)
      radius: Commons.Style.space(2)
      color: row.swatchColor
      anchors.left: parent.left
      anchors.verticalCenter: parent.verticalCenter
    }

    Text {
      id: labelText_
      textFormat: Text.PlainText
      text: row.labelText
      color: Commons.Color.popups.text
      font.family: Commons.Style.font.family
      font.pixelSize: Commons.Style.font.body
      anchors.left: swatch.right
      anchors.leftMargin: Commons.Style.space(8)
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

  // ---- One horizontal stacked bar with an optional leading label and a
  // hover tooltip carrying the exact percentages.
  component BarRow: Item {
    id: barRow
    property string rowLabel: ""
    property var day: null
    property bool highlightLabel: false
    readonly property bool hasData: day !== null && day.activeMinutes > 0
    width: parent ? parent.width : 0
    height: Commons.Style.space(14)

    Text {
      id: label
      visible: barRow.rowLabel !== ""
      textFormat: Text.PlainText
      text: barRow.rowLabel
      color: barRow.highlightLabel ? Commons.Color.popups.text : Commons.Color.muted
      font.family: Commons.Style.font.family
      font.pixelSize: Commons.Style.font.bodySmall
      width: visible ? Commons.Style.space(40) : 0
      elide: Text.ElideRight
      anchors.left: parent.left
      anchors.verticalCenter: parent.verticalCenter
    }

    Item {
      id: barArea
      height: parent.height
      anchors.left: label.right
      anchors.leftMargin: label.visible ? Commons.Style.space(8) : 0
      anchors.right: parent.right

      readonly property real unit: width / 100.0

      // Idle fills the whole pill; keyboard and mouse stack over it from the
      // left. Only the pill's leading edge is rounded — inner seams stay
      // square so the three segments read as one bar.
      Rectangle {
        anchors.fill: parent
        radius: Commons.Style.space(2)
        color: root.idleColor
      }

      Rectangle {
        id: kbSeg
        x: 0
        width: barArea.unit * (barRow.hasData ? barRow.day.kbPct : 0)
        height: parent.height
        topLeftRadius: Commons.Style.space(2)
        bottomLeftRadius: Commons.Style.space(2)
        color: root.kbColor
      }

      Rectangle {
        x: kbSeg.width
        width: barArea.unit * (barRow.hasData ? barRow.day.mousePct : 0)
        height: parent.height
        color: root.mouseColor
      }
    }

    MouseArea {
      id: hoverArea
      anchors.fill: parent
      hoverEnabled: true
      acceptedButtons: Qt.NoButton
    }

    PanelToolTip {
      visible: hoverArea.containsMouse
      text: barRow.hasData ? root.pctText(barRow.day) : strings.t("pulse.noDataDay")
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
      // The card sizes itself from the content's implicitHeight; without it
      // the card collapses to nothing and the column overflows below it.
      implicitHeight: contentColumn.implicitHeight
      clip: true
      onCloseRequested: root.close()

      Column {
        id: contentColumn
        anchors.fill: parent
        spacing: Commons.Style.space(10)

        // ---- Header: title on the left, refresh action on the right.
        Item {
          width: parent ? parent.width : 0
          height: Math.max(titleText.implicitHeight, refreshButton.height)

          Text {
            id: titleText
            textFormat: Text.PlainText
            text: strings.t("pulse.title")
            color: Commons.Color.popups.text
            font.family: Commons.Style.font.family
            font.pixelSize: Commons.Style.font.body
            font.weight: Font.DemiBold
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
          }

          PanelActionButton {
            id: refreshButton
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            iconText: "\uF021"
            tooltipText: strings.t("pulse.refresh")
            onClicked: root.refresh()
          }
        }

        Text {
          textFormat: Text.PlainText
          text: root.hasData
            ? strings.t("pulse.since").arg(root.formatTime(root.stats.firstTsMs))
            : strings.t("pulse.noData")
          color: Commons.Color.muted
          font.family: Commons.Style.font.family
          font.pixelSize: Commons.Style.font.bodySmall
        }

        // ---- Today: the percentage numbers.
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

        // ---- Last 7 days: one stacked bar per day, hover for the split.
        PanelSectionHeader {
          text: strings.t("pulse.sectionWeek")
          font.family: Commons.Style.font.family
        }

        Repeater {
          model: 7

          BarRow {
            required property int modelData

            // Fresh JS Date in the binding: calling locale formatting on a
            // `property date` receiver throws "incompatible arguments" in
            // this Qt build (plain new Date() receivers are fine).
            rowLabel: {
                var d = new Date()
                d.setDate(d.getDate() - (6 - modelData))
                return d.toLocaleDateString(Qt.locale(Commons.I18n.formatLocale), "ddd")
            }

            highlightLabel: modelData === 6
            day: root.days.length === 7 ? root.days[modelData] : null
          }
        }

        // ---- Total across the week.
        PanelSectionHeader {
          text: strings.t("pulse.sectionTotal")
          font.family: Commons.Style.font.family
        }

        BarRow {
          rowLabel: ""
          day: root.total
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
