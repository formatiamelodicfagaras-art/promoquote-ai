"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import {
  fetchUsers,
  createUser,
  updateUser,
  deleteUser,
} from "@/lib/api";
import type { User } from "@/types";
import {
  Users,
  Plus,
  Pencil,
  Trash2,
  X,
  Shield,
  ShieldOff,
  UserCheck,
  UserX,
} from "lucide-react";

interface UserFormData {
  name: string;
  email: string;
  password: string;
  is_admin: boolean;
}

const emptyForm: UserFormData = {
  name: "",
  email: "",
  password: "",
  is_admin: false,
};

export default function AdminPage() {
  const { isAdmin, isLoading } = useAuth();
  const router = useRouter();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Modal state
  const [showModal, setShowModal] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [form, setForm] = useState<UserFormData>(emptyForm);
  const [formError, setFormError] = useState("");
  const [formLoading, setFormLoading] = useState(false);

  // Delete confirmation
  const [deletingUser, setDeletingUser] = useState<User | null>(null);

  const loadUsers = useCallback(async () => {
    try {
      setLoading(true);
      const data = await fetchUsers();
      setUsers(data);
    } catch {
      setError("Nu s-au putut incarca utilizatorii");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isLoading) return;
    if (!isAdmin) {
      router.replace("/chat");
      return;
    }
    loadUsers();
  }, [isAdmin, isLoading, router, loadUsers]);

  function openAdd() {
    setEditingUser(null);
    setForm(emptyForm);
    setFormError("");
    setShowModal(true);
  }

  function openEdit(user: User) {
    setEditingUser(user);
    setForm({
      name: user.name,
      email: user.email,
      password: "",
      is_admin: user.is_admin,
    });
    setFormError("");
    setShowModal(true);
  }

  async function handleSubmit() {
    setFormError("");
    setFormLoading(true);
    try {
      if (editingUser) {
        const payload: Record<string, unknown> = {
          name: form.name,
          email: form.email,
          is_admin: form.is_admin,
        };
        if (form.password) payload.password = form.password;
        await updateUser(editingUser.id, payload as Parameters<typeof updateUser>[1]);
      } else {
        if (!form.password) {
          setFormError("Parola este obligatorie");
          setFormLoading(false);
          return;
        }
        await createUser({
          name: form.name,
          email: form.email,
          password: form.password,
          is_admin: form.is_admin,
        });
      }
      setShowModal(false);
      loadUsers();
    } catch (err: unknown) {
      setFormError(
        err instanceof Error ? err.message : "Operatiune esuata"
      );
    } finally {
      setFormLoading(false);
    }
  }

  async function handleDelete() {
    if (!deletingUser) return;
    try {
      await deleteUser(deletingUser.id);
      setDeletingUser(null);
      loadUsers();
    } catch {
      setError("Nu s-a putut sterge utilizatorul");
      setDeletingUser(null);
    }
  }

  async function toggleActive(user: User) {
    try {
      await updateUser(user.id, { is_active: !user.is_active });
      loadUsers();
    } catch {
      setError("Nu s-a putut actualiza statusul");
    }
  }

  if (isLoading || (!isAdmin && !isLoading)) {
    return null;
  }

  return (
    <div className="h-full overflow-y-auto p-3 sm:p-6">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4 sm:mb-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-accent/10 flex items-center justify-center flex-shrink-0">
              <Users size={20} className="text-accent" />
            </div>
            <div>
              <h1 className="text-lg sm:text-xl font-bold text-dark-50">
                Administrare Utilizatori
              </h1>
              <p className="text-xs sm:text-sm text-dark-300">
                Gestioneaza conturile de utilizator
              </p>
            </div>
          </div>
          <button
            onClick={openAdd}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-accent hover:bg-accent-hover text-white text-sm font-medium transition-colors self-start sm:self-auto"
          >
            <Plus size={16} />
            Utilizator nou
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3 text-sm text-red-400 mb-4">
            {error}
            <button
              onClick={() => setError("")}
              className="ml-2 text-red-300 hover:text-red-200"
            >
              <X size={14} />
            </button>
          </div>
        )}

        {/* Table */}
        {loading ? (
          <div className="flex justify-center py-16">
            <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <div className="bg-dark-800/50 backdrop-blur-xl border border-[--border] rounded-2xl overflow-x-auto">
            <table className="w-full min-w-[600px]">
              <thead>
                <tr className="border-b border-[--border]">
                  <th className="text-left text-xs font-semibold text-dark-200 uppercase tracking-wider px-5 py-3">
                    Nume
                  </th>
                  <th className="text-left text-xs font-semibold text-dark-200 uppercase tracking-wider px-5 py-3">
                    Email
                  </th>
                  <th className="text-center text-xs font-semibold text-dark-200 uppercase tracking-wider px-5 py-3">
                    Rol
                  </th>
                  <th className="text-center text-xs font-semibold text-dark-200 uppercase tracking-wider px-5 py-3">
                    Status
                  </th>
                  <th className="text-right text-xs font-semibold text-dark-200 uppercase tracking-wider px-5 py-3">
                    Actiuni
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[--border]">
                {users.map((u) => (
                  <tr
                    key={u.id}
                    className="hover:bg-dark-700/20 transition-colors"
                  >
                    <td className="px-5 py-3">
                      <p className="text-sm font-medium text-dark-50">
                        {u.name}
                      </p>
                    </td>
                    <td className="px-5 py-3">
                      <p className="text-sm text-dark-200">{u.email}</p>
                    </td>
                    <td className="px-5 py-3 text-center">
                      {u.is_admin ? (
                        <span className="inline-flex items-center gap-1 text-xs font-medium text-amber-400 bg-amber-500/10 px-2.5 py-1 rounded-lg">
                          <Shield size={12} />
                          Admin
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-xs font-medium text-dark-200 bg-dark-600/30 px-2.5 py-1 rounded-lg">
                          <ShieldOff size={12} />
                          Utilizator
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3 text-center">
                      <button
                        onClick={() => toggleActive(u)}
                        title={u.is_active ? "Dezactiveaza" : "Activeaza"}
                      >
                        {u.is_active ? (
                          <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-400 bg-emerald-500/10 px-2.5 py-1 rounded-lg">
                            <UserCheck size={12} />
                            Activ
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-xs font-medium text-red-400 bg-red-500/10 px-2.5 py-1 rounded-lg">
                            <UserX size={12} />
                            Inactiv
                          </span>
                        )}
                      </button>
                    </td>
                    <td className="px-5 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => openEdit(u)}
                          className="p-2 rounded-lg text-dark-300 hover:text-dark-50 hover:bg-dark-600/30 transition-colors"
                          title="Editeaza"
                        >
                          <Pencil size={14} />
                        </button>
                        <button
                          onClick={() => setDeletingUser(u)}
                          className="p-2 rounded-lg text-dark-300 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                          title="Sterge"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {users.length === 0 && (
                  <tr>
                    <td
                      colSpan={5}
                      className="px-5 py-12 text-center text-sm text-dark-300"
                    >
                      Nu exista utilizatori
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Add/Edit Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-dark-800 border border-[--border] rounded-2xl w-full max-w-md p-6 shadow-2xl">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-bold text-dark-50">
                {editingUser ? "Editeaza utilizator" : "Utilizator nou"}
              </h2>
              <button
                onClick={() => setShowModal(false)}
                className="p-1.5 rounded-lg text-dark-300 hover:text-dark-50 hover:bg-dark-600/30 transition-colors"
              >
                <X size={18} />
              </button>
            </div>

            {formError && (
              <div className="bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3 text-sm text-red-400 mb-4">
                {formError}
              </div>
            )}

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-dark-100 mb-1.5">
                  Nume
                </label>
                <input
                  type="text"
                  required
                  value={form.name}
                  onChange={(e) =>
                    setForm({ ...form, name: e.target.value })
                  }
                  className="w-full px-4 py-2.5 rounded-xl bg-dark-700/50 border border-[--border] text-dark-50 text-sm focus:outline-none focus:border-accent/40 focus:ring-1 focus:ring-accent/20 transition-colors"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-dark-100 mb-1.5">
                  Email
                </label>
                <input
                  type="email"
                  required
                  value={form.email}
                  onChange={(e) =>
                    setForm({ ...form, email: e.target.value })
                  }
                  className="w-full px-4 py-2.5 rounded-xl bg-dark-700/50 border border-[--border] text-dark-50 text-sm focus:outline-none focus:border-accent/40 focus:ring-1 focus:ring-accent/20 transition-colors"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-dark-100 mb-1.5">
                  Parola{editingUser && " (lasa gol pentru a nu schimba)"}
                </label>
                <input
                  type="password"
                  value={form.password}
                  onChange={(e) =>
                    setForm({ ...form, password: e.target.value })
                  }
                  placeholder={editingUser ? "••••••••" : ""}
                  className="w-full px-4 py-2.5 rounded-xl bg-dark-700/50 border border-[--border] text-dark-50 placeholder-dark-400 text-sm focus:outline-none focus:border-accent/40 focus:ring-1 focus:ring-accent/20 transition-colors"
                />
              </div>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() =>
                    setForm({ ...form, is_admin: !form.is_admin })
                  }
                  className={`relative w-10 h-5 rounded-full transition-colors ${
                    form.is_admin ? "bg-accent" : "bg-dark-600"
                  }`}
                >
                  <span
                    className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                      form.is_admin ? "translate-x-5" : ""
                    }`}
                  />
                </button>
                <span className="text-sm text-dark-100">Administrator</span>
              </div>
            </div>

            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setShowModal(false)}
                className="px-4 py-2.5 rounded-xl text-sm font-medium text-dark-200 hover:text-dark-50 bg-dark-700/50 border border-[--border] hover:bg-dark-600/50 transition-colors"
              >
                Anuleaza
              </button>
              <button
                onClick={handleSubmit}
                disabled={formLoading}
                className="px-4 py-2.5 rounded-xl text-sm font-medium text-white bg-accent hover:bg-accent-hover transition-colors disabled:opacity-50"
              >
                {formLoading
                  ? "Se salveaza..."
                  : editingUser
                  ? "Salveaza"
                  : "Creaza"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deletingUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-dark-800 border border-[--border] rounded-2xl w-full max-w-sm p-6 shadow-2xl">
            <h2 className="text-lg font-bold text-dark-50 mb-2">
              Sterge utilizator
            </h2>
            <p className="text-sm text-dark-200 mb-5">
              Esti sigur ca vrei sa stergi utilizatorul{" "}
              <span className="font-medium text-dark-50">
                {deletingUser.name}
              </span>
              ? Aceasta actiune nu poate fi anulata.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setDeletingUser(null)}
                className="px-4 py-2.5 rounded-xl text-sm font-medium text-dark-200 hover:text-dark-50 bg-dark-700/50 border border-[--border] hover:bg-dark-600/50 transition-colors"
              >
                Anuleaza
              </button>
              <button
                onClick={handleDelete}
                className="px-4 py-2.5 rounded-xl text-sm font-medium text-white bg-red-600 hover:bg-red-500 transition-colors"
              >
                Sterge
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
