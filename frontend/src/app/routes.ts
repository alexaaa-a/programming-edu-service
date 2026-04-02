import { createBrowserRouter } from "react-router";
import AppShell from "./AppShell";
import Registration from "./screens/Registration";
import Login from "./screens/Login";
import DirectionSelection from "./screens/DirectionSelection";
import LevelSelection from "./screens/LevelSelection";
import Dashboard from "./screens/Dashboard";
import Profile from "./screens/Profile";
import ChangePassword from "./screens/ChangePassword";
import Statistics from "./screens/Statistics";
import AdminPanel from "./screens/AdminPanel";
import TaskPage from "./screens/TaskPage";
import TeamChat from "./screens/TeamChat";
import SprintReport from "./screens/SprintReport";

export const router = createBrowserRouter([
  {
    path: "/",
    Component: AppShell,
    children: [
      {
        index: true,
        Component: Registration,
      },
      {
        path: "login",
        Component: Login,
      },
      {
        path: "direction",
        Component: DirectionSelection,
      },
      {
        path: "level",
        Component: LevelSelection,
      },
      {
        path: "dashboard",
        Component: Dashboard,
      },
      {
        path: "profile",
        Component: Profile,
      },
      {
        path: "profile/password",
        Component: ChangePassword,
      },
      {
        path: "statistics",
        Component: Statistics,
      },
      {
        path: "admin",
        Component: AdminPanel,
      },
      {
        path: "task/:taskId",
        Component: TaskPage,
      },
      {
        path: "chat",
        Component: TeamChat,
      },
      {
        path: "report/:submissionId",
        Component: SprintReport,
      },
    ],
  },
]);
