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
  readonly property var apps: hostWidget && hostWidget.apps !== undefined ? hostWidget.apps : null
  readonly property bool appsUnavailable: hostWidget && hostWidget.appsUnavailable === true
  readonly property string lastError: hostWidget ? hostWidget.lastError : ""
  readonly property string awUrl: hostWidget ? hostWidget.awUrl : ""
  readonly property bool hasData: stats !== null && stats.spanMinutes > 0

  // Fixed column widths so the tornado's central axis aligns across rows.
  readonly property int appsNameWidth: Commons.Style.space(88)
  readonly property int appsPctWidth: Commons.Style.space(36)

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

  // ---- Tornado row: app name on the left, then a central axis in the bar
  // zone — keyboard grows left (bright), mouse grows right (mid); each side
  // is its own 100% scale. Total share right-aligned; the hover tooltip
  // carries the exact split and the raw app class.
  component TornadoRow: Item {
    id: tornadoRow
    property var record: null
    // Scale floor: with very little data the largest share can be tiny;
    // capping the stretch at 25% keeps early-session bars from overstating.
    property real maxShare: 100
    readonly property bool hasData: record !== null && record.activeMinutes > 0
    width: parent ? parent.width : 0
    height: Commons.Style.space(14)

    Text {
      id: appName
      textFormat: Text.PlainText
      text: tornadoRow.record
        ? (tornadoRow.record.app === "other" ? strings.t("pulse.other") : tornadoRow.record.label)
        : ""
      // Same size/style as the highlighted "today" day label in Last 7 days.
      color: Commons.Color.popups.text
      font.family: Commons.Style.font.family
      font.pixelSize: Commons.Style.font.bodySmall
      width: root.appsNameWidth
      elide: Text.ElideRight
      anchors.left: parent.left
      anchors.verticalCenter: parent.verticalCenter
    }

    Item {
      id: barZone
      height: parent.height
      anchors.left: appName.right
      anchors.leftMargin: Commons.Style.space(8)
      anchors.right: pctText.left
      anchors.rightMargin: Commons.Style.space(8)
      anchors.verticalCenter: parent.verticalCenter

      // The axis sits in the middle of the zone. The scale is data-driven:
      // one common unit for both sides (comparisons stay honest), sized so
      // the largest single bar reaches its panel edge — floored so sparse
      // early data can't overstate.
      readonly property real half: width / 2
      readonly property real unit: half / Math.max(25, tornadoRow.maxShare)

      Rectangle {
        x: barZone.half - width / 2
        width: 1
        height: parent.height
        color: Commons.Util.alpha(Commons.Color.accent, 0.35)
      }

      Rectangle {
        x: barZone.half - width
        width: barZone.unit * (tornadoRow.hasData ? tornadoRow.record.kbTotalShare : 0)
        height: parent.height
        // Rounded at the outer end, flat at the axis — matching the day
        // bars' leading-edge treatment.
        topLeftRadius: Commons.Style.space(2)
        bottomLeftRadius: Commons.Style.space(2)
        color: root.kbColor
      }

      Rectangle {
        x: barZone.half
        width: barZone.unit * (tornadoRow.hasData ? tornadoRow.record.mouseTotalShare : 0)
        height: parent.height
        topRightRadius: Commons.Style.space(2)
        bottomRightRadius: Commons.Style.space(2)
        color: root.mouseColor
      }
    }

    Text {
      id: pctText
      textFormat: Text.PlainText
      text: tornadoRow.hasData ? Commons.I18n.formatNumber(tornadoRow.record.pct) + "%" : "—"
      color: Commons.Color.popups.text
      font.family: Commons.Style.font.family
      font.pixelSize: Commons.Style.font.body
      width: root.appsPctWidth
      horizontalAlignment: Text.AlignRight
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
    }

    MouseArea {
      id: hoverArea
      anchors.fill: parent
      hoverEnabled: true
      acceptedButtons: Qt.NoButton
    }

    PanelToolTip {
      visible: hoverArea.containsMouse
      text: tornadoRow.hasData
        ? (tornadoRow.record.app + " · "
          + strings.t("pulse.keyboard") + " " + Commons.I18n.formatNumber(Math.round(tornadoRow.record.kbShare)) + "% · "
          + strings.t("pulse.mouse") + " " + Commons.I18n.formatNumber(Math.round(tornadoRow.record.mouseShare)) + "%")
        : strings.t("pulse.noDataDay")
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

        // ---- Top apps (today): tornado rows — keyboard grows left, mouse
        // grows right from the central axis; hover for the exact split. From
        // the window watcher's spans joined onto the input minutes. Hidden
        // until a window watcher has run at least once.
        PanelSectionHeader {
          text: strings.t("pulse.sectionApps")
          font.family: Commons.Style.font.family
          visible: root.apps !== null || root.appsUnavailable
        }

        Item {
          width: parent ? parent.width : 0
          height: keyCaption.implicitHeight
          visible: root.apps !== null

          readonly property real zoneLeft: root.appsNameWidth + Commons.Style.space(8)
          readonly property real zoneWidth: width - zoneLeft - (root.appsPctWidth + Commons.Style.space(8))
          readonly property real axisX: zoneLeft + zoneWidth / 2

          Text {
            id: keyCaption
            textFormat: Text.PlainText
            text: strings.t("pulse.keyboard")
            color: Commons.Color.muted
            font.family: Commons.Style.font.family
            font.pixelSize: Commons.Style.font.bodySmall
            width: parent.zoneWidth / 2 - Commons.Style.space(4)
            horizontalAlignment: Text.AlignRight
            x: parent.zoneLeft
            anchors.verticalCenter: parent.verticalCenter
          }

          Rectangle {
            x: parent.axisX - width / 2
            width: 1
            height: parent.height
            color: Commons.Util.alpha(Commons.Color.accent, 0.35)
          }

          Text {
            textFormat: Text.PlainText
            text: strings.t("pulse.mouse")
            color: Commons.Color.muted
            font.family: Commons.Style.font.family
            font.pixelSize: Commons.Style.font.bodySmall
            x: parent.axisX + Commons.Style.space(4)
            anchors.verticalCenter: parent.verticalCenter
          }
        }

        Repeater {
          model: root.apps !== null ? root.apps.apps.length : 0

          TornadoRow {
            required property int modelData

            record: root.apps.apps[modelData]
            maxShare: root.apps.maxShare
          }
        }

        Text {
          width: parent ? parent.width : 0
          visible: root.appsUnavailable && root.apps === null
          wrapMode: Text.Wrap
          textFormat: Text.PlainText
          text: strings.t("pulse.appsHint")
          color: Commons.Color.muted
          font.family: Commons.Style.font.family
          font.pixelSize: Commons.Style.font.bodySmall
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
